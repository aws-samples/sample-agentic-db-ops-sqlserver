# Updated: 2026-03-15
from strands import Agent, tool
from strands.models import BedrockModel
import boto3
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

# Import local agents for testing
from database_health_agent_interactive import agent as health_agent
from query_performance_agent_interactive import agent as performance_agent
from security_audit_agent_interactive import agent as security_agent
from data_lifecycle_agent_interactive import agent as lifecycle_agent
try:
    from actions_agent_interactive import agent as actions_agent
except ImportError:
    actions_agent = None

# Configuration from environment variables.
SNS_TOPIC_NAME = os.getenv('SNS_TOPIC_NAME', 'sqlserver-database-alerts')
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID', 'dbops-infra-sqlserver')

# Define the AI model
model = BedrockModel(
    model_id=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
    region_name=AWS_REGION,
    temperature=0.3
)

# Helper function to invoke other agents
def _sub_agents() -> Dict[str, Any]:
    return {
        'database_health_agent': health_agent,
        'query_performance_agent': performance_agent,
        'security_audit_agent': security_agent,
        'data_lifecycle_agent': lifecycle_agent,
        'actions_agent': actions_agent,
    }


# Sub-agents stream to stdout by default. When the Supervisor issues two delegations in the
# same turn they interleave character-by-character and the transcript becomes unreadable.
# Only the Supervisor should print.
#
# NOTE: assign a no-op CALLABLE, not None. Strands only converts callback_handler=None into
# a null handler inside Agent.__init__; assigning None after construction leaves a literal
# None that the run loop then calls, raising "TypeError: 'NoneType' object is not callable".
def _silent_callback_handler(*args, **kwargs):
    return None


for _name, _sub in _sub_agents().items():
    if _sub is not None:
        try:
            _sub.callback_handler = _silent_callback_handler
        except Exception:
            pass


def _extract_text(response) -> str:
    """Join all text blocks. response.message['content'][0] is not always a text block."""
    try:
        blocks = response.message.get('content', []) or []
    except AttributeError:
        return str(response)
    parts = [b['text'] for b in blocks if isinstance(b, dict) and 'text' in b]
    return '\n'.join(parts) if parts else '(no text content returned)'


_AGENT_ALIASES = {
    'health': 'database_health_agent',
    'database_health': 'database_health_agent',
    'query': 'query_performance_agent',
    'performance': 'query_performance_agent',
    'query_performance': 'query_performance_agent',
    'security': 'security_audit_agent',
    'security_audit': 'security_audit_agent',
    'lifecycle': 'data_lifecycle_agent',
    'data_lifecycle': 'data_lifecycle_agent',
    'action': 'actions_agent',
    'actions': 'actions_agent',
}


def _resolve_agent_name(name: str) -> str:
    """Map a loosely-specified agent name onto a canonical key."""
    key = (name or '').strip().lower().replace('-', '_').replace(' ', '_')
    if key in _sub_agents():
        return key
    if key in _AGENT_ALIASES:
        return _AGENT_ALIASES[key]
    stem = key[:-6] if key.endswith('_agent') else key
    return _AGENT_ALIASES.get(stem, key)


def invoke_agent_runtime(agent_name: str, prompt: str) -> Dict[str, Any]:
    """Invoke local agent directly for testing"""
    agents = _sub_agents()
    try:
        resolved = _resolve_agent_name(agent_name)
        agent = agents.get(resolved)
        if not agent:
            return {'error': f"Agent '{agent_name}' not found",
                    'valid_agents': sorted(k for k, v in agents.items() if v is not None)}

        # Reset the sub-agent's conversation before each delegation. These agents are
        # stateless read-only tool executors; without this their history grows across the
        # session and PHASE 5 verification answers from pre-fix data instead of re-querying.
        try:
            agent.messages = []
        except Exception:
            pass

        response = agent(prompt)
        return {'response': _extract_text(response)}
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}

# ===== AGENT INVOCATION TOOLS =====

@tool
def invoke_health_check() -> Dict[str, Any]:
    """Invoke Database Health Agent for comprehensive health check"""
    prompt = """Provide a comprehensive health check including:
    - Wait event breakdown by type (call get_wait_events)
    - Current CPU utilization
    - Memory usage
    - Database connections
    - Database load
    - Storage space
    - IOPS and latency

    Return the raw tool output for every item above."""

    return invoke_agent_runtime('database_health_agent', prompt)

@tool
def invoke_wait_analysis() -> Dict[str, Any]:
    """PHASE 1a. Identify which resource is constrained, as a share of total database load.

    This is the fork point of the whole investigation and must run before any drill-down.
    Returns wait events by type plus load and CPU for context.
    """
    prompt = """Return raw tool output only, for these three tools:
    1. get_wait_events - wait event breakdown by type
    2. get_database_load - Active Average Sessions timeline
    3. get_cpu_utilization - CPU timeline

    Do not interpret. Return the numbers."""

    return invoke_agent_runtime('database_health_agent', prompt)

@tool
def invoke_performance_analysis() -> Dict[str, Any]:
    """Invoke Query Performance Agent for performance analysis"""
    prompt = """Analyze query performance including:
    - Top CPU-consuming queries
    - Wait statistics
    - Slow running queries
    - Blocking sessions
    - Missing index recommendations
    
    Identify performance bottlenecks."""
    
    return invoke_agent_runtime('query_performance_agent', prompt)

@tool
def invoke_triage_scan() -> Dict[str, Any]:
    """PHASE 1b. Find the consumer: every live request with waits, memory grants and blocking.

    Returns session_id values. Feed the worst offender's session_id into invoke_plan_analysis.
    Call get_memory_grants too when wait analysis showed RESOURCE_SEMAPHORE.
    """
    prompt = """PHASE 1. Return raw tool output only:
    1. get_active_requests - all live requests with wait_type, granted_memory_mb, elapsed_seconds
    2. get_memory_grants - grant queue state and per-query grants
    3. get_blocking_sessions - blocking chains

    Include every session_id. Do not interpret or rank."""

    return invoke_agent_runtime('query_performance_agent', prompt)

@tool
def invoke_plan_analysis(session_id: int) -> Dict[str, Any]:
    """PHASE 2. Get the in-flight execution plan for one session, with ACTUAL row counts.

    This is the root cause step. The returned plan summary contains estimate-vs-actual row
    ratios per operator and plan warnings (implicit conversions, spills, missing statistics).
    You MUST call this before making any claim about why a query is slow.

    Args:
        session_id: session_id from invoke_triage_scan
    """
    prompt = f"""PHASE 2. Call get_live_execution_plan with session_id={session_id}.
    Return the raw tool output including every operator, the estimate/actual ratios,
    all plan warnings and the memory grant detail. Do not interpret."""

    return invoke_agent_runtime('query_performance_agent', prompt)

@tool
def invoke_schema_analysis(table_name: str) -> Dict[str, Any]:
    """PHASE 3. Get schema, existing indexes and statistics health for one table.

    Required before recommending a fix. Existing indexes prevent duplicate recommendations;
    statistics health tells you whether a cheap UPDATE STATISTICS would resolve a bad
    cardinality estimate instead of an index.

    Args:
        table_name: table to inspect, e.g. "Orders"
    """
    prompt = f"""PHASE 3. Return raw tool output only, for table '{table_name}':
    1. get_table_schema('{table_name}')
    2. get_existing_indexes('{table_name}')
    3. get_statistics_health('{table_name}')
    4. suggest_indexes('{table_name}')

    Do not interpret."""

    return invoke_agent_runtime('query_performance_agent', prompt)

@tool
def verify_action_outcome(baseline_aas: float,
                          baseline_cpu_percent: float,
                          wait_seconds: int = 90) -> Dict[str, Any]:
    """PHASE 5. Wait, re-measure, and compare against the Phase 1 baseline.

    The verdict is COMPUTED, not judged - use it as given. Call this after any executed action,
    passing the numbers you recorded in Phase 1.

    Waits first, because a new plan is only picked up by NEW executions. Statements already
    running keep their original plan, so measuring immediately after an index is created shows
    no change even when the fix is correct.

    Returns baseline vs current AAS and CPU, the percentage change, the now-dominant wait
    event, and a verdict of IMPROVED / UNCHANGED / WORSE.

    Args:
        baseline_aas: db.load.avg (Active Average Sessions) recorded in Phase 1
        baseline_cpu_percent: CPU utilization percentage recorded in Phase 1
        wait_seconds: settle time before measuring (default 90, capped at 300)
    """
    import time as _time
    try:
        wait_seconds = max(0, min(int(wait_seconds), 300))
        if wait_seconds:
            _time.sleep(wait_seconds)

        rds = boto3.client('rds', region_name=AWS_REGION)
        inst = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)['DBInstances'][0]
        resource_id = inst['DbiResourceId']
        instance_class = inst.get('DBInstanceClass')

        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=5)

        pi = boto3.client('pi', region_name=AWS_REGION)
        resp = pi.get_resource_metrics(
            ServiceType='RDS',
            Identifier=resource_id,
            StartTime=start,
            EndTime=end,
            PeriodInSeconds=60,
            MetricQueries=[{'Metric': 'db.load.avg',
                            'GroupBy': {'Group': 'db.wait_event', 'Limit': 7}}],
        )

        def _latest(points):
            vals = [p['Value'] for p in points if p.get('Value') is not None]
            return vals[-1] if vals else None

        current_aas = None
        waits = {}
        for item in resp.get('MetricList', []):
            dims = item['Key'].get('Dimensions')
            val = _latest(item.get('DataPoints', []))
            if val is None:
                continue
            if not dims:
                current_aas = val
            else:
                waits[dims.get('db.wait_event.name', 'unknown')] = round(val, 2)

        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        cw_resp = cw.get_metric_statistics(
            Namespace='AWS/RDS', MetricName='CPUUtilization',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
            StartTime=start, EndTime=end, Period=60, Statistics=['Average'],
        )
        dps = sorted(cw_resp.get('Datapoints', []), key=lambda d: d['Timestamp'])
        current_cpu = round(dps[-1]['Average'], 2) if dps else None

        dominant_wait = max(waits, key=waits.get) if waits else None

        def _pct(before, after):
            if before in (None, 0) or after is None:
                return None
            return round((after - before) / before * 100.0, 1)

        aas_change = _pct(baseline_aas, current_aas)
        cpu_change = _pct(baseline_cpu_percent, current_cpu)

        # Deterministic verdict, driven by AAS (the load measure), CPU as corroboration.
        if current_aas is None:
            verdict = 'INCONCLUSIVE'
        elif aas_change is not None and aas_change <= -30:
            verdict = 'IMPROVED'
        elif aas_change is not None and aas_change >= 10:
            verdict = 'WORSE'
        else:
            verdict = 'UNCHANGED'

        return {
            'verdict': verdict,
            'waited_seconds': wait_seconds,
            'instance_class': instance_class,
            'baseline': {'aas': baseline_aas, 'cpu_percent': baseline_cpu_percent},
            'current': {'aas': round(current_aas, 2) if current_aas is not None else None,
                        'cpu_percent': current_cpu},
            'change_percent': {'aas': aas_change, 'cpu': cpu_change},
            'dominant_wait_now': dominant_wait,
            'wait_breakdown_now': waits,
            'next_step': ('Report before/after and stop.' if verdict == 'IMPROVED' else
                          'Return to PHASE 1 and re-triage from current data. Do not repeat the '
                          'same action. Check whether the top consumer or constrained resource '
                          'has changed, and whether pre-existing sessions are still running '
                          'their original plans.'),
        }
    except Exception as e:
        return {'verdict': 'INCONCLUSIVE', 'error': f'{type(e).__name__}: {e}'}


@tool
def invoke_plan_change_check(object_name: str = None,
                             query_fragment: str = None,
                             within_minutes: int = 10,
                             baseline_plan_hash: str = None) -> Dict[str, Any]:
    """PHASE 5a. Confirm a NEW execution plan was compiled and is in use, for ANY object.

    Direct evidence that an index, statistics update or recompile took effect. Stronger than
    inferring it from CPU, which other workload can confound. Also returns per-execution
    avg_cpu_ms and avg_logical_reads for the CURRENT plan only, because the DMV counters reset
    on recompile - that is the cleanest before/after measure of whether the new plan is better.

    Verdicts: PLAN_CHANGED / PLAN_UNCHANGED / NO_DATA.

    Args:
        object_name: Any object, e.g. "sp_MonthlyOrderReport", "dbo.SomeView"
        query_fragment: For ad-hoc SQL with no owning object
        within_minutes: A plan compiled this recently counts as new (default 10)
        baseline_plan_hash: query_plan_hash captured before the change, if you have it
    """
    args = []
    if object_name:
        args.append(f"object_name='{object_name}'")
    if query_fragment:
        args.append(f"query_fragment='{query_fragment}'")
    args.append(f"within_minutes={within_minutes}")
    if baseline_plan_hash:
        args.append(f"baseline_plan_hash='{baseline_plan_hash}'")

    prompt = (f"PHASE 5. Call verify_plan_changed({', '.join(args)}). "
              "Return the raw tool output including the verdict, plan ages, "
              "plan_generation_num, query_plan_hash values and the per-execution averages. "
              "Do not interpret.")

    return invoke_agent_runtime('query_performance_agent', prompt)


@tool
def invoke_history_analysis() -> Dict[str, Any]:
    """PHASE 4 (optional). Query Store history and regression detection.

    Only useful if Query Store is enabled. Answers "did this regress and when".
    Skip on a short-lived instance with no history.
    """
    prompt = """PHASE 4. Call check_query_store_enabled first. If it reports enabled, also call
    get_query_store_regressed_queries and get_query_store_top_queries with metric='cpu'.
    If it reports disabled, return that fact and stop. Return raw tool output only."""

    return invoke_agent_runtime('query_performance_agent', prompt)

@tool
def invoke_security_audit() -> Dict[str, Any]:
    """Invoke Security Audit Agent for security review"""
    prompt = """Perform security audit including:
    - TDE encryption status
    - Backup encryption
    - Failed login attempts (last 7 days)
    - RDS events and configuration changes
    - CloudTrail activity
    - RDS security settings
    
    Identify security concerns and suspicious activities."""
    
    return invoke_agent_runtime('security_audit_agent', prompt)

@tool
def invoke_lifecycle_check() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent for comprehensive storage and lifecycle review"""
    prompt = """Review data lifecycle including:
    - Storage usage and growth trends
    - IOPS, throughput, and latency trends
    - Storage type and upgrade recommendations
    - TempDB analysis and bottlenecks
    - Largest tables and indexes
    - Backup status
    - Fragmentation status
    
    Identify storage optimization opportunities."""
    
    return invoke_agent_runtime('data_lifecycle_agent', prompt)

@tool
def invoke_backup_check() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent specifically for backup status"""
    prompt = """Check backup status only:
    - Use check_backup_status tool
    - Backup retention period
    - Recent snapshots
    - Latest restorable time
    
    Report backup compliance."""
    
    return invoke_agent_runtime('data_lifecycle_agent', prompt)

@tool
def invoke_tempdb_analysis() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent specifically for TempDB analysis"""
    prompt = """Analyze TempDB only:
    - Use analyze_tempdb_bottleneck tool
    - TempDB size and usage
    - Configuration issues
    - Contention and I/O problems
    
    Report TempDB bottlenecks."""
    
    return invoke_agent_runtime('data_lifecycle_agent', prompt)

@tool
def invoke_custom_agent_query(agent_name: str, question: str) -> Dict[str, Any]:
    """Invoke a specific agent with a custom question"""
    return invoke_agent_runtime(agent_name, question)

@tool
def invoke_actions_agent(action_request: str) -> Dict[str, Any]:
    """Invoke the Actions Agent to execute ONE specific database optimization action.

    IMPORTANT: Send ONE action at a time. Do NOT batch multiple actions in a single call.
    Call this tool multiple times sequentially if you need multiple actions executed.

    The Actions Agent can: create indexes, update statistics, rebuild/reorganize indexes,
    recompile objects (sp_recompile), and force/unforce query plans.

    All MEDIUM risk actions (index creation) require human approval via email before execution.

    Examples of good action requests:
    - "Create index: <the exact CREATE INDEX statement from suggest_indexes for the offending query>"
    - "Update statistics on <table> table"
    - "Rebuild index <index name> on <table>"
    - "Recompile dbo.sp_MonthlyOrderReport"

    Examples of BAD requests (do NOT do this):
    - "Fix all the slow queries" (too broad)
    - "Create 5 indexes" (batched — send one at a time)

    Args:
        action_request: ONE specific action with the exact SQL or parameters needed
    """
    if actions_agent is None:
        return {'error': 'Actions Agent not available. Ensure actions_agent_interactive.py is in the same directory.'}
    return invoke_agent_runtime('actions_agent', action_request)

# ===== SNS NOTIFICATION TOOL =====

@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send an email notification via SNS. Severity: INFO, WARNING, CRITICAL"""
    try:
        sns_client = boto3.client('sns', region_name=AWS_REGION)
        response = sns_client.list_topics()
        topic_arn = None
        
        for topic in response.get('Topics', []):
            if topic['TopicArn'].endswith(f":{SNS_TOPIC_NAME}"):
                topic_arn = topic['TopicArn']
                break
        
        if not topic_arn:
            return {'status': 'error', 'error': f"SNS topic '{SNS_TOPIC_NAME}' not found"}
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        formatted_message = f"""
SQL SERVER SUPERVISOR ALERT
============================
Timestamp: {timestamp}
Severity: {severity}
Subject: {subject}

{message}

---
Sent by AgentCore Supervisor Agent
"""
        
        sns_subject = f"[{severity}] {subject}"[:100]
        response = sns_client.publish(
            TopicArn=topic_arn,
            Subject=sns_subject,
            Message=formatted_message
        )
        
        return {
            'status': 'success',
            'message_id': response.get('MessageId'),
            'severity': severity
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

@tool
def generate_daily_report() -> Dict[str, Any]:
    """Generate comprehensive daily operational report from all agents"""
    try:
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'health_check': invoke_health_check(),
            'performance_analysis': invoke_performance_analysis(),
            'security_audit': invoke_security_audit(),
            'lifecycle_check': invoke_lifecycle_check()
        }
        
        # Compile summary
        summary = f"""
DAILY SQL SERVER OPERATIONS REPORT
===================================
Generated: {report['timestamp']}

DATABASE HEALTH:
{report['health_check'].get('response', report['health_check'].get('error', 'N/A'))}

QUERY PERFORMANCE:
{report['performance_analysis'].get('response', report['performance_analysis'].get('error', 'N/A'))}

SECURITY AUDIT:
{report['security_audit'].get('response', report['security_audit'].get('error', 'N/A'))}

DATA LIFECYCLE:
{report['lifecycle_check'].get('response', report['lifecycle_check'].get('error', 'N/A'))}

---
End of Report
"""
        
        return {
            'status': 'success',
            'report': summary,
            'detailed_results': report
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

# ===== AGENT CONFIGURATION =====

system_prompt = """You are the Supervisor Agent for SQL Server database operations. You are the ONLY reasoner in this system.

The agents you invoke are tool executors. They return RAW DATA and never judge, rank or recommend.
ALL interpretation is yours: read the raw metrics, identify the mechanism, decide the action.

=====================================================================
TRIAGE WORKFLOW - follow the phases in order. Do not skip a phase.
=====================================================================

PHASE 1 - ATTRIBUTION: what resource is constrained, and who is consuming it?
  1a. invoke_wait_analysis  -> wait events by type, AAS, CPU
  1b. invoke_triage_scan    -> live requests with waits/grants/blocking, and session_ids

  State both of these numerically:
    - the constrained resource, as a percentage of total AAS
    - the share of load attributable to the top query

  This instance may be short-lived with no historical baseline. Do NOT ask whether current
  values are "normal" - attribute the load you can see to the queries causing it.

  Wait type -> constrained resource:
    CPU                            -> compute
    RESOURCE_SEMAPHORE             -> memory grants
    PAGEIOLATCH_* / WRITELOG       -> storage IO
    LCK_M_*                        -> blocking
    CXPACKET / CXCONSUMER          -> parallelism skew
    ASYNC_NETWORK_IO               -> client not consuming results
    SLEEP_BPOOL_STEAL              -> buffer pool pressure

PHASE 2 - MECHANISM: why is that query slow?
  invoke_plan_analysis(session_id) using the worst session_id from Phase 1.

  You may NOT assert a cause until you have the plan. High logical_reads alone is a symptom,
  not a mechanism. Read from the plan summary:
    - top_row_estimate_skew: actual_vs_estimate_ratio >> 1 means a cardinality error
    - plan_warnings PlanAffectingConvert    -> implicit conversion, predicate non-SARGable
    - plan_warnings SpillToTempDb           -> memory grant too small for actual volume
    - plan_warnings ColumnsWithNoStatistics -> estimates have no basis
    - plan_warnings NoJoinPredicate         -> cartesian product
    - actual_executions >> 1 on an inner operator -> per-row execution (correlated
      subquery or scalar UDF)
    - a join whose actual_rows greatly exceeds the sum of its inputs -> wrong join grain
      (many-to-many fan-out)

PHASE 3 - FIX VIABILITY: is an index enough, or is a code change required?
  invoke_schema_analysis(table_name) for each table named in the offending plan operators.
  Check existing indexes before proposing any index. Check statistics health before blaming
  the plan, because stale statistics are far cheaper to fix than anything else.

PHASE 4 - ACTION: choose the cheapest fix that addresses the Phase 2 mechanism.

  MECHANISM                                    -> FIX                -> HOW
  stale statistics (modified_percent >= 20)     UPDATE STATISTICS     execute (LOW)
  plus estimate/actual skew on that table
  ---------------------------------------------------------------------------------------
  a cached plan predates an index or statistics  sp_recompile          execute (LOW)
  change, or a plan has gone bad and no known
  good plan exists to force
  ---------------------------------------------------------------------------------------
  SARGable predicate scanning a table with      CREATE INDEX          execute (MEDIUM,
  no covering index, estimates roughly right                          email approval)
  ---------------------------------------------------------------------------------------
  plan regression, known good plan exists       force plan            execute (MEDIUM,
                                                                      email approval)
  ---------------------------------------------------------------------------------------
  implicit conversion (PlanAffectingConvert)    RECOMMEND REWRITE     do NOT execute,
  function wrapping an indexed column                                 output the T-SQL
  scalar UDF or correlated subquery per row
  wrong join grain / many-to-many fan-out
  ---------------------------------------------------------------------------------------
  grant starvation from concurrency             RECOMMEND throttling  do NOT execute,
  (RESOURCE_SEMAPHORE + many identical queries) or session termination state it plainly

  RULES FOR ACTIONS:
  - An index CANNOT fix a wrong join grain, an implicit conversion, or a scalar UDF. If
    Phase 2 shows one of those, recommending an index is wrong. Recommend the rewrite.
  - When you recommend a rewrite you MUST output the corrected T-SQL in full, plus one line
    on what changed and why it removes the mechanism. That is the deliverable.
  - A new index does NOT affect a query already executing; the running plan was compiled at
    start. Say so when in-flight sessions are the problem, and note the fix applies to
    subsequent executions only.
  - LOAD GATE: before executing any action, check Phase 1. If AAS exceeds the vCPU count, or
    RESOURCE_SEMAPHORE is the dominant wait, then LOW risk actions lose their auto-execute
    privilege, because UPDATE STATISTICS, CREATE INDEX and REBUILD all add load.
    This gate NEVER cancels an action. It ONLY downgrades auto-execute to approval-required.
    You MUST still submit the action through invoke_actions_agent so a human can approve it.
  - invoke_actions_agent IS the approval mechanism. It classifies risk and emails the human an
    approve/reject link for MEDIUM and HIGH risk actions. Printing SQL for the user to run by
    hand is NOT a substitute for submitting the action. If a fix is warranted, submit it.
  - Never withhold the DURABLE FIX because IMMEDIATE RELIEF requires a human. The two tracks
    are independent: report the relief as advisory AND submit the durable fix in the same turn.
  - Plan refresh is part of the action, not a separate decision. CREATE INDEX and UPDATE
    STATISTICS already invalidate dependent cached plans, and create_index additionally runs
    sp_recompile on the table. Do NOT request a plan refresh as its own action, and NEVER
    request DBCC FREEPROCCACHE without an argument - that flushes the whole instance cache and
    causes a server-wide recompile storm. If one specific object needs it, use recompile_object.
  - Call invoke_actions_agent exactly ONCE PER CYCLE, with ONE specific action. If several
    indexes are needed, submit only the highest-impact one and list the others as follow-ups.

PHASE 5 - VERIFY, THEN LOOP IF IT DID NOT WORK:
  Before acting, record the Phase 1 baseline: AAS and CPU percent. You need them here.

  Check TWO independent signals. They fail for different reasons, so do not merge them.

  5a. DID THE PLAN CHANGE?
      invoke_plan_change_check(object_name=<the object you fixed>)
      Works for any object, not just procedures. Verdicts:
        PLAN_CHANGED    -> the fix is live. Go to 5b.
        PLAN_UNCHANGED  -> the change has NOT taken effect. Do not blame the fix itself.
                           Usual cause: the object is still executing a statement compiled
                           before the change. Check invoke_triage_scan, and say the object must
                           finish or be terminated first.
        NO_DATA         -> no completed execution since the change. Wait and re-check; these
                           DMVs only record COMPLETED executions.

  5b. DID IT ACTUALLY HELP?
      verify_action_outcome(baseline_aas=<phase 1 AAS>, baseline_cpu_percent=<phase 1 CPU>)
      It waits before measuring, because a new plan is only used by NEW executions.
      The verdict is COMPUTED - use it as given, do not substitute your own judgement.
        IMPROVED      -> report baseline vs current numbers and STOP.
        UNCHANGED     -> go to step 6.
        WORSE         -> go to step 6, and say plainly that the action did not help.
        INCONCLUSIVE  -> report why, and treat as UNCHANGED.

      Also compare avg_cpu_ms and avg_logical_reads from 5a. Those counters reset on recompile,
      so they describe the new plan alone and are not confounded by other workload. If the plan
      changed but per-execution cost did not fall, the fix was the wrong fix - an index cannot
      help that query and you should recommend a rewrite instead.

  6. On UNCHANGED or WORSE, do NOT stop and do NOT repeat the same action. Return to PHASE 1
     and re-triage from current data. Read dominant_wait_now in the verification result - it
     often names the next bottleneck.
  7. ITERATION CAP: at most 3 triage -> action -> verify cycles per user request. On the third
     unsuccessful cycle, STOP and report every action attempted, its measured effect, and what
     you recommend a human investigate.

  Interpreting the two signals together:
    plan changed + cost fell      -> fix worked
    plan changed + cost unchanged -> wrong fix; recommend a rewrite
    plan unchanged                -> fix not yet live; in-flight sessions are the blocker
    no data                       -> nothing has completed yet; wait, do not conclude

=====================================================================
DATA INTEGRITY RULES
=====================================================================
1. DO NOT GUESS. Reason only from returned data.
2. An EMPTY result is not a finding. suggest_indexes returning zero rows means the optimizer
   logged no recommendation. It does NOT mean an index would not help, and it supports no
   conclusion. Distinguish "returned empty" from "tool failed".
3. Before stating a cause you MUST list every tool that errored or returned no data under a
   "DATA GAPS" heading. If wait analysis or the execution plan is unavailable, label the
   diagnosis provisional.
4. Every number you cite must come from a tool result. Never invent values.

=====================================================================
OUTPUT FORMAT - two tracks. Under 250 words, or longer if a rewrite is included.
=====================================================================
SEVERITY: CRITICAL / WARNING / INFO
  CRITICAL: AAS > 2x vCPU, or CPU > 90%, or connections near max, or freeable memory < 1 GB
  WARNING:  AAS > vCPU, or CPU > 70%, or a dominant non-CPU wait
ATTRIBUTION: <resource> is N% of load; <query> is M% of load
MECHANISM: one sentence naming the plan-level cause, with the operator and the ratio
EVIDENCE: specific numbers from the plan and the metrics
IMMEDIATE RELIEF: what restores service now (may be advisory only)
DURABLE FIX: the action taken, or the rewrite recommended with full T-SQL
DATA GAPS: tools that failed or returned nothing, or "none"

Do not ask "Would you like me to...?" - either act within your authority or state the
recommendation. Send at most ONE email per interaction.

ADDITIONAL SAFETY RULES:
- NEVER recommend or suggest killing sessions (KILL command). Instead, identify the root
  cause of why sessions are long-running or blocking (missing index, bad query design,
  connection leak) and recommend fixing THAT. Flag problematic sessions for human awareness only.
- Do NOT send email notifications unless the user explicitly says "send email" or "notify team".
- ALWAYS flag CRITICAL conditions at the TOP of your response regardless of what the user
  asked: storage near zero, connections near max, memory exhausted, replication lag. These
  are emergencies that override the users question.
- If remediation requires MORE THAN ONE change: present the plan and wait for explicit
  confirmation before executing. This applies regardless of whether the user said "fix it".

Agents you coordinate:
1. Database Health Agent   - CloudWatch + Performance Insights
2. Query Performance Agent - DMVs, live plans, schema, Query Store
3. Security Audit Agent    - encryption, logins, RDS events, CloudTrail
4. Data Lifecycle Agent    - storage, IOPS, TempDB, backups
5. Actions Agent           - executes ONE approved optimization

Other tools: invoke_health_check, invoke_security_audit, invoke_lifecycle_check,
invoke_backup_check, invoke_tempdb_analysis, invoke_history_analysis,
invoke_custom_agent_query, generate_daily_report, send_email_notification."""


agent = Agent(
    system_prompt=system_prompt,
    model=model,
    tools=[
        # Phase 1 - attribution
        invoke_wait_analysis,
        invoke_triage_scan,
        # Phase 2 - mechanism
        invoke_plan_analysis,
        # Phase 3 - fix viability
        invoke_schema_analysis,
        # Phase 4 - history (optional)
        invoke_history_analysis,
        # Phase 4/5 - action and verification
        invoke_actions_agent,
        invoke_plan_change_check,
        verify_action_outcome,
        # Broad / other domains
        invoke_health_check,
        invoke_performance_analysis,
        invoke_security_audit,
        invoke_lifecycle_check,
        invoke_backup_check,
        invoke_tempdb_analysis,
        invoke_custom_agent_query,
        generate_daily_report,
        send_email_notification
    ]
)

if __name__ == "__main__":
    print("Supervisor Agent - Coordinate all database operations and generate reports.")
    print("Type 'exit' or 'quit' to end.\n")
    
    while True:
        prompt = input("Your prompt: ")
        
        if prompt.lower() in ['exit', 'quit']:
            print("Goodbye!")
            break
        
        if prompt.strip():
            # The Supervisor's own callback handler already streams the answer to stdout.
            # Printing response text again would duplicate the entire response.
            try:
                agent(prompt)
            except Exception as e:
                print(f"\n[error] {type(e).__name__}: {e}")
                print("Session preserved - try again or rephrase.")
            print()


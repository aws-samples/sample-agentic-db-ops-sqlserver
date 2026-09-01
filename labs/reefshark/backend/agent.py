"""
TravelAI Agent - Conversational travel planning assistant
Uses a state machine to guide users through trip planning
"""
from typing import Optional
import json
import random


class TravelAgent:
    """Agentic travel assistant that guides users through booking"""

    def __init__(self):
        self.sessions = {}

    def _get_session(self, session_id: str) -> dict:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "state": "greeting",
                "trip": {
                    "destination": None,
                    "origin": None,
                    "dates": None,
                    "travelers": None,
                    "budget": None,
                    "interests": [],
                },
                "selections": {
                    "flight": None,
                    "hotel": None,
                    "activities": [],
                    "car": None,
                },
                "history": [],
            }
        return self.sessions[session_id]

    def process_message(self, message: str, session_id: str) -> dict:
        session = self._get_session(session_id)
        session["history"].append({"role": "user", "content": message})

        state = session["state"]
        response = self._handle_state(state, message, session)

        session["history"].append({"role": "assistant", "content": response["message"]})

        return response

    def _handle_state(self, state: str, message: str, session: dict) -> dict:
        handlers = {
            "greeting": self._handle_greeting,
            "ask_destination": self._handle_destination,
            "ask_dates": self._handle_dates,
            "ask_travelers": self._handle_travelers,
            "ask_budget": self._handle_budget,
            "ask_interests": self._handle_interests,
            "show_flights": self._handle_flights,
            "show_hotels": self._handle_hotels,
            "show_activities": self._handle_activities,
            "show_cars": self._handle_cars,
            "summary": self._handle_summary,
        }

        handler = handlers.get(state, self._handle_greeting)
        return handler(message, session)

    def _handle_greeting(self, message: str, session: dict) -> dict:
        session["state"] = "ask_destination"
        return {
            "message": "✈️ Hey there! I'm your AI travel assistant. I'll help you plan and book an amazing trip!\n\nLet's start — **where would you like to go?** (You can name a city, country, or just say something like 'somewhere warm' and I'll suggest options!)",
            "type": "text",
            "suggestions": ["Paris, France", "Tokyo, Japan", "New York, USA", "Bali, Indonesia", "Somewhere warm"],
        }

    def _handle_destination(self, message: str, session: dict) -> dict:
        session["trip"]["destination"] = message.strip()
        session["state"] = "ask_dates"
        dest = session["trip"]["destination"]
        return {
            "message": f"🌍 Great choice! **{dest}** is amazing. I'll find the best options for you.\n\n📅 **When are you planning to travel?** Give me your approximate dates or a month you're thinking about.",
            "type": "text",
            "suggestions": ["Next weekend", "December 2024", "Dec 15-22", "I'm flexible"],
        }

    def _handle_dates(self, message: str, session: dict) -> dict:
        session["trip"]["dates"] = message.strip()
        session["state"] = "ask_travelers"
        return {
            "message": f"📅 Got it — **{message.strip()}** works!\n\n👥 **How many travelers?** (Just you, a couple, family, group?)",
            "type": "text",
            "suggestions": ["Just me", "2 travelers", "Family of 4", "Group of 6"],
        }

    def _handle_travelers(self, message: str, session: dict) -> dict:
        session["trip"]["travelers"] = message.strip()
        session["state"] = "ask_budget"
        return {
            "message": f"👥 Perfect — **{message.strip()}**.\n\n💰 **What's your budget range?** This helps me find the best value options.",
            "type": "text",
            "suggestions": ["Budget ($500-1000)", "Mid-range ($1000-3000)", "Luxury ($3000+)", "No limit"],
        }

    def _handle_budget(self, message: str, session: dict) -> dict:
        session["trip"]["budget"] = message.strip()
        session["state"] = "ask_interests"
        return {
            "message": f"💰 Budget noted: **{message.strip()}**\n\n🎯 **What are you into?** Pick a few interests so I can personalize your trip:",
            "type": "text",
            "suggestions": [
                "🏖️ Beaches & Relaxation",
                "🏛️ Culture & History",
                "🍜 Food & Dining",
                "🎢 Adventure & Sports",
                "🛍️ Shopping",
                "🌿 Nature & Outdoors",
            ],
        }

    def _handle_interests(self, message: str, session: dict) -> dict:
        session["trip"]["interests"] = [i.strip() for i in message.split(",")]
        session["state"] = "show_flights"

        dest = session["trip"]["destination"]
        dates = session["trip"]["dates"]

        return {
            "message": f"🎯 Love it! Based on your preferences, I'm now searching for the best options...\n\n✈️ Here are **flights to {dest}** around {dates}:",
            "type": "flights",
            "data": self._get_mock_flights(dest),
            "action_prompt": "Pick a flight (1-3) or say 'skip' to move on to hotels",
        }

    def _handle_flights(self, message: str, session: dict) -> dict:
        if "skip" not in message.lower():
            session["selections"]["flight"] = message.strip()

        session["state"] = "show_hotels"
        dest = session["trip"]["destination"]

        return {
            "message": f"✅ Flight noted!\n\n🏨 Now let's find you a place to stay in **{dest}**:",
            "type": "hotels",
            "data": self._get_mock_hotels(dest),
            "action_prompt": "Pick a hotel (1-3) or say 'skip'",
        }

    def _handle_hotels(self, message: str, session: dict) -> dict:
        if "skip" not in message.lower():
            session["selections"]["hotel"] = message.strip()

        session["state"] = "show_activities"
        dest = session["trip"]["destination"]

        return {
            "message": f"✅ Hotel booked!\n\n🎉 Let me find some amazing **activities in {dest}**:",
            "type": "activities",
            "data": self._get_mock_activities(dest),
            "action_prompt": "Pick activities (e.g., '1,3') or say 'skip'",
        }

    def _handle_activities(self, message: str, session: dict) -> dict:
        if "skip" not in message.lower():
            session["selections"]["activities"] = [a.strip() for a in message.split(",")]

        session["state"] = "show_cars"
        dest = session["trip"]["destination"]

        return {
            "message": f"✅ Activities added!\n\n🚗 Need a **rental car in {dest}**?",
            "type": "cars",
            "data": self._get_mock_cars(dest),
            "action_prompt": "Pick a car (1-3) or say 'no thanks'",
        }

    def _handle_cars(self, message: str, session: dict) -> dict:
        if "no" not in message.lower() and "skip" not in message.lower():
            session["selections"]["car"] = message.strip()

        session["state"] = "summary"

        trip = session["trip"]
        selections = session["selections"]

        total = random.randint(800, 3500)

        return {
            "message": f"🎉 **Your trip is ready!**\n\n📍 **Destination:** {trip['destination']}\n📅 **Dates:** {trip['dates']}\n👥 **Travelers:** {trip['travelers']}\n💰 **Estimated Total:** ${total}\n\n---\n\nWould you like to **confirm and book** or make any changes?",
            "type": "summary",
            "data": {
                "trip": trip,
                "selections": selections,
                "estimated_total": total,
            },
            "action_prompt": "Say 'book it!' to confirm or tell me what to change",
        }

    def _handle_summary(self, message: str, session: dict) -> dict:
        if "book" in message.lower():
            # Reset session for next trip
            session["state"] = "greeting"
            return {
                "message": "🎊 **Booking confirmed!** Your amazing trip is all set!\n\n📧 You'll receive confirmation emails shortly.\n\n---\n\nWant to plan another trip? Just say hi!",
                "type": "confirmation",
                "data": {"booking_id": f"TRV-{random.randint(10000, 99999)}"},
            }
        else:
            session["state"] = "ask_destination"
            return {
                "message": "No problem! Let's make some changes. **What would you like to adjust?**",
                "type": "text",
                "suggestions": ["Change destination", "Different dates", "Different hotel", "Start over"],
            }

    # Mock data generators
    def _get_mock_flights(self, destination: str):
        airlines = ["United", "Delta", "American", "JetBlue", "Southwest"]
        return [
            {
                "id": i + 1,
                "airline": random.choice(airlines),
                "departure": f"{random.randint(6,22):02d}:{random.choice(['00','30'])}",
                "arrival": f"{random.randint(6,22):02d}:{random.choice(['00','30'])}",
                "duration": f"{random.randint(2,14)}h {random.randint(0,59)}m",
                "stops": random.choice(["Nonstop", "1 stop", "2 stops"]),
                "price": random.randint(199, 899),
                "destination": destination,
            }
            for i in range(3)
        ]

    def _get_mock_hotels(self, destination: str):
        hotel_names = [
            f"The Grand {destination} Hotel",
            f"{destination} Boutique Suites",
            f"Oceanview Resort & Spa",
        ]
        return [
            {
                "id": i + 1,
                "name": hotel_names[i],
                "rating": round(random.uniform(4.0, 5.0), 1),
                "price_per_night": random.randint(89, 450),
                "amenities": random.sample(
                    ["Pool", "Spa", "Gym", "Restaurant", "Bar", "WiFi", "Parking", "Beach Access"],
                    k=4,
                ),
                "destination": destination,
            }
            for i in range(3)
        ]

    def _get_mock_activities(self, destination: str):
        activity_types = [
            {"name": f"City Walking Tour of {destination}", "category": "Culture", "duration": "3h"},
            {"name": f"Food & Wine Tasting Experience", "category": "Food", "duration": "4h"},
            {"name": f"Adventure Helicopter Ride", "category": "Adventure", "duration": "1h"},
            {"name": f"Local Cooking Class", "category": "Food", "duration": "2.5h"},
            {"name": f"Sunset Cruise", "category": "Relaxation", "duration": "2h"},
        ]
        selected = random.sample(activity_types, k=3)
        return [
            {
                "id": i + 1,
                "name": a["name"],
                "category": a["category"],
                "duration": a["duration"],
                "price": random.randint(29, 199),
                "rating": round(random.uniform(4.2, 5.0), 1),
            }
            for i, a in enumerate(selected)
        ]

    def _get_mock_cars(self, destination: str):
        cars = [
            {"type": "Economy", "model": "Toyota Corolla"},
            {"type": "SUV", "model": "Ford Explorer"},
            {"type": "Luxury", "model": "BMW 5 Series"},
        ]
        return [
            {
                "id": i + 1,
                "type": c["type"],
                "model": c["model"],
                "price_per_day": random.randint(35, 150),
                "features": random.sample(
                    ["GPS", "Bluetooth", "Backup Camera", "Heated Seats", "Sunroof", "Apple CarPlay"],
                    k=3,
                ),
            }
            for i, c in enumerate(cars)
        ]

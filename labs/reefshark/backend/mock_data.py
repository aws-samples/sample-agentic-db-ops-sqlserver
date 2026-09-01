"""
Mock travel data for flights, hotels, activities, and rental cars
"""

flights = [
    {"id": 1, "airline": "United Airlines", "origin": "NYC", "destination": "LAX", "departure": "08:00", "arrival": "11:30", "duration": "5h 30m", "stops": "Nonstop", "price": 349, "class": "Economy"},
    {"id": 2, "airline": "Delta", "origin": "NYC", "destination": "LAX", "departure": "10:15", "arrival": "13:45", "duration": "5h 30m", "stops": "Nonstop", "price": 399, "class": "Economy"},
    {"id": 3, "airline": "JetBlue", "origin": "NYC", "destination": "LAX", "departure": "14:00", "arrival": "17:30", "duration": "5h 30m", "stops": "Nonstop", "price": 289, "class": "Economy"},
    {"id": 4, "airline": "American Airlines", "origin": "NYC", "destination": "PAR", "departure": "19:00", "arrival": "08:30", "duration": "7h 30m", "stops": "Nonstop", "price": 649, "class": "Economy"},
    {"id": 5, "airline": "Air France", "origin": "NYC", "destination": "PAR", "departure": "22:00", "arrival": "11:30", "duration": "7h 30m", "stops": "Nonstop", "price": 599, "class": "Economy"},
    {"id": 6, "airline": "United Airlines", "origin": "NYC", "destination": "TYO", "departure": "12:00", "arrival": "15:00+1", "duration": "14h", "stops": "Nonstop", "price": 899, "class": "Economy"},
    {"id": 7, "airline": "ANA", "origin": "NYC", "destination": "TYO", "departure": "13:30", "arrival": "16:30+1", "duration": "14h", "stops": "Nonstop", "price": 949, "class": "Economy"},
    {"id": 8, "airline": "Southwest", "origin": "LAX", "destination": "NYC", "departure": "06:00", "arrival": "14:00", "duration": "5h", "stops": "Nonstop", "price": 259, "class": "Economy"},
    {"id": 9, "airline": "Delta", "origin": "SFO", "destination": "NYC", "departure": "08:00", "arrival": "16:30", "duration": "5h 30m", "stops": "Nonstop", "price": 379, "class": "Economy"},
    {"id": 10, "airline": "Emirates", "origin": "NYC", "destination": "DXB", "departure": "22:30", "arrival": "19:00+1", "duration": "12h 30m", "stops": "Nonstop", "price": 799, "class": "Economy"},
]

hotels = [
    {"id": 1, "name": "The Grand Palace Hotel", "city": "Los Angeles", "rating": 4.8, "price_per_night": 289, "amenities": ["Pool", "Spa", "Gym", "Restaurant", "Valet Parking"], "type": "Luxury"},
    {"id": 2, "name": "Sunset Boulevard Inn", "city": "Los Angeles", "rating": 4.3, "price_per_night": 159, "amenities": ["Pool", "WiFi", "Breakfast", "Parking"], "type": "Mid-range"},
    {"id": 3, "name": "LA Budget Stays", "city": "Los Angeles", "rating": 3.9, "price_per_night": 79, "amenities": ["WiFi", "Parking", "Coffee Bar"], "type": "Budget"},
    {"id": 4, "name": "Hôtel de la Paix", "city": "Paris", "rating": 4.9, "price_per_night": 450, "amenities": ["Spa", "Restaurant", "Bar", "Concierge", "Room Service"], "type": "Luxury"},
    {"id": 5, "name": "Le Petit Marais", "city": "Paris", "rating": 4.5, "price_per_night": 189, "amenities": ["WiFi", "Breakfast", "Bar", "Bike Rental"], "type": "Boutique"},
    {"id": 6, "name": "Paris Hostel Central", "city": "Paris", "rating": 4.0, "price_per_night": 59, "amenities": ["WiFi", "Kitchen", "Lounge"], "type": "Budget"},
    {"id": 7, "name": "Tokyo Imperial Suites", "city": "Tokyo", "rating": 4.9, "price_per_night": 520, "amenities": ["Onsen", "Restaurant", "Gym", "Spa", "Garden"], "type": "Luxury"},
    {"id": 8, "name": "Shibuya Stay", "city": "Tokyo", "rating": 4.4, "price_per_night": 145, "amenities": ["WiFi", "Laundry", "Convenience Store", "Metro Access"], "type": "Mid-range"},
    {"id": 9, "name": "Manhattan Skyline Hotel", "city": "New York", "rating": 4.6, "price_per_night": 350, "amenities": ["Rooftop Bar", "Gym", "Restaurant", "Concierge"], "type": "Luxury"},
    {"id": 10, "name": "Brooklyn Boutique B&B", "city": "New York", "rating": 4.3, "price_per_night": 175, "amenities": ["Breakfast", "Garden", "WiFi", "Bikes"], "type": "Boutique"},
]

activities = [
    {"id": 1, "name": "Hollywood Sign Hike", "city": "Los Angeles", "category": "Outdoors", "duration": "3h", "price": 0, "rating": 4.6},
    {"id": 2, "name": "Universal Studios Tour", "city": "Los Angeles", "category": "Entertainment", "duration": "8h", "price": 129, "rating": 4.7},
    {"id": 3, "name": "Santa Monica Pier & Beach", "city": "Los Angeles", "category": "Relaxation", "duration": "4h", "price": 0, "rating": 4.4},
    {"id": 4, "name": "Eiffel Tower Skip-the-Line", "city": "Paris", "category": "Sightseeing", "duration": "2h", "price": 45, "rating": 4.8},
    {"id": 5, "name": "Louvre Museum Guided Tour", "city": "Paris", "category": "Culture", "duration": "3h", "price": 65, "rating": 4.9},
    {"id": 6, "name": "Seine River Dinner Cruise", "city": "Paris", "category": "Dining", "duration": "2.5h", "price": 89, "rating": 4.7},
    {"id": 7, "name": "Tsukiji Fish Market Tour", "city": "Tokyo", "category": "Food", "duration": "3h", "price": 55, "rating": 4.8},
    {"id": 8, "name": "Shibuya & Harajuku Walking Tour", "city": "Tokyo", "category": "Culture", "duration": "4h", "price": 35, "rating": 4.6},
    {"id": 9, "name": "Traditional Tea Ceremony", "city": "Tokyo", "category": "Culture", "duration": "1.5h", "price": 40, "rating": 4.9},
    {"id": 10, "name": "Broadway Show Tickets", "city": "New York", "category": "Entertainment", "duration": "3h", "price": 149, "rating": 4.8},
    {"id": 11, "name": "Central Park Bike Tour", "city": "New York", "category": "Outdoors", "duration": "2h", "price": 45, "rating": 4.5},
    {"id": 12, "name": "Statue of Liberty & Ellis Island", "city": "New York", "category": "Sightseeing", "duration": "5h", "price": 29, "rating": 4.7},
]

rental_cars = [
    {"id": 1, "type": "Economy", "model": "Toyota Corolla", "location": "Los Angeles", "price_per_day": 45, "features": ["GPS", "Bluetooth", "Backup Camera"]},
    {"id": 2, "type": "SUV", "model": "Ford Explorer", "location": "Los Angeles", "price_per_day": 85, "features": ["GPS", "Bluetooth", "3rd Row", "Roof Rack"]},
    {"id": 3, "type": "Luxury", "model": "BMW 5 Series", "location": "Los Angeles", "price_per_day": 150, "features": ["GPS", "Leather", "Heated Seats", "Premium Sound"]},
    {"id": 4, "type": "Economy", "model": "Renault Clio", "location": "Paris", "price_per_day": 35, "features": ["GPS", "Manual", "Compact"]},
    {"id": 5, "type": "Mid-size", "model": "Peugeot 3008", "location": "Paris", "price_per_day": 65, "features": ["GPS", "Automatic", "Bluetooth", "Parking Sensors"]},
    {"id": 6, "type": "Compact", "model": "Toyota Yaris", "location": "Tokyo", "price_per_day": 40, "features": ["GPS", "ETC Card", "Bluetooth"]},
    {"id": 7, "type": "Economy", "model": "Hyundai Elantra", "location": "New York", "price_per_day": 55, "features": ["GPS", "Bluetooth", "Backup Camera"]},
    {"id": 8, "type": "SUV", "model": "Jeep Grand Cherokee", "location": "New York", "price_per_day": 95, "features": ["GPS", "4WD", "Bluetooth", "Apple CarPlay"]},
]

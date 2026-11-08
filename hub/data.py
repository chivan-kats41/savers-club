"""Sample data for 1K Saver Club dashboards (Uganda focused).

Direct Python port of the original lib/sample-data.ts so every page shows
the same numbers as the Lovable/React version.
"""

AREAS = [
    "Mutungo", "Kitintale", "Luzira", "Kireka", "Bweyogerere",
    "Makindye", "Nansana", "Nakawa", "Ntinda", "Katabi", "Entebbe", "Kampala", "Wakiso",
]

SUBSCRIPTION_GROWTH = [
    {"month": "Jan", "members": 420, "renewals": 360},
    {"month": "Feb", "members": 760, "renewals": 640},
    {"month": "Mar", "members": 1180, "renewals": 980},
    {"month": "Apr", "members": 1740, "renewals": 1420},
    {"month": "May", "members": 2410, "renewals": 2010},
    {"month": "Jun", "members": 3260, "renewals": 2710},
    {"month": "Jul", "members": 4180, "renewals": 3520},
    {"month": "Aug", "members": 5240, "renewals": 4380},
    {"month": "Sep", "members": 6520, "renewals": 5410},
    {"month": "Oct", "members": 7980, "renewals": 6412},
]

REDEMPTIONS_BY_CATEGORY = [
    {"name": "Daily Basket", "value": 4280},
    {"name": "Pharmacy", "value": 1340},
    {"name": "School Items", "value": 980},
    {"name": "Restaurants", "value": 1620},
    {"name": "Phone & Data", "value": 1180},
    {"name": "Services", "value": 720},
]

SAVINGS_BY_CATEGORY = [
    {"name": "Daily Basket", "value": 8_640_000},
    {"name": "Pharmacy", "value": 3_120_000},
    {"name": "School Items", "value": 2_400_000},
    {"name": "Restaurants", "value": 1_980_000},
    {"name": "Phone & Data", "value": 1_540_000},
    {"name": "Services", "value": 1_120_000},
]

ROUTE_EARNINGS = [
    {"route": "Mutungo→CBD", "earnings": 480_000},
    {"route": "Kireka→Nakawa", "earnings": 360_000},
    {"route": "Nansana→CBD", "earnings": 540_000},
    {"route": "Ntinda→Bweyogerere", "earnings": 290_000},
    {"route": "Katabi→Entebbe", "earnings": 220_000},
]

COMPLAINTS_BY_TYPE = [
    {"type": "Fake deal", "count": 12},
    {"type": "Code refused", "count": 28},
    {"type": "Item unavailable", "count": 19},
    {"type": "Wrong price", "count": 14},
    {"type": "Failed delivery", "count": 9},
    {"type": "Rider misconduct", "count": 5},
    {"type": "Pickup point issue", "count": 7},
    {"type": "Payment issue", "count": 11},
]

RECENT_ACTIVITY = [
    {"who": "Sarah N.", "what": "claimed offer “2kg Sugar @ UGX 7,800”", "where": "Kitintale", "when": "2 min ago"},
    {"who": "Boda Musoke", "what": "completed shared route Mutungo→CBD (12 packages)", "where": "Mutungo", "when": "8 min ago"},
    {"who": "Kireka Mini Mart", "what": "added 4 new offers", "where": "Kireka", "when": "14 min ago"},
    {"who": "Agent Wakiso", "what": "verified merchant “Nansana Pharmacy”", "where": "Nansana", "when": "32 min ago"},
    {"who": "Brian K.", "what": "paid monthly subscription UGX 1,000", "where": "Ntinda", "when": "1 hr ago"},
    {"who": "Aisha M.", "what": "reported issue: code not accepted", "where": "Bweyogerere", "when": "2 hr ago"},
]

TODAYS_RISK_ALERTS = [
    {"kind": "Code refused", "note": "Nakawa Phone Shop refused 3 valid codes in 1 hour", "severity": "high"},
    {"kind": "Fake deal", "note": "“Cheap data 10GB @ 5K” reported by 4 members", "severity": "high"},
    {"kind": "Failed delivery", "note": "Boda Patrick · 2 failed pickups in Kireka", "severity": "medium"},
    {"kind": "Commission unpaid", "note": "Route Mutungo→CBD · UGX 24,000 outstanding (4 days)", "severity": "medium"},
    {"kind": "Payment failed", "note": "62 members · MoMo timeout", "severity": "low"},
    {"kind": "Offer expired but visible", "note": "12 expired offers still showing on app", "severity": "low"},
    {"kind": "Repeated claims", "note": "Same code claimed 6 times — Kitintale Mini Mart", "severity": "high"},
]

PENDING_APPROVALS = {
    "merchants": [
        {"name": "Bweyogerere Fresh Market", "area": "Bweyogerere", "category": "Daily Basket", "submitted": "Today"},
        {"name": "Luzira Pharmacy Plus", "area": "Luzira", "category": "Pharmacy", "submitted": "Yesterday"},
        {"name": "Nansana School Supplies", "area": "Nansana", "category": "School Items", "submitted": "2 days ago"},
    ],
    "riders": [
        {"name": "Joseph Ssempa", "stage": "Mutungo Stage", "area": "Mutungo", "submitted": "Today"},
        {"name": "Patrick Okello", "stage": "Kireka Stage", "area": "Kireka", "submitted": "Today"},
    ],
    "offers": [
        {"item": "5L Cooking Oil", "merchant": "Ntinda Wholesale", "normal": 28000, "member": 24500},
        {"item": "Charcoal Sack (medium)", "merchant": "Makindye Energy", "normal": 65000, "member": 58000},
        {"item": "Lunch Combo (rice+beans+meat)", "merchant": "Mama Joy Kitchen", "normal": 8000, "member": 6500},
    ],
}

BASKET_ITEMS = [
    {"item": "Rice (1kg)", "normal": 4500, "member": 3800, "seller": "Nakawa Wholesale"},
    {"item": "Sugar (1kg)", "normal": 4200, "member": 3700, "seller": "Kitintale Mini Mart"},
    {"item": "Beans (1kg)", "normal": 3800, "member": 3200, "seller": "Bweyogerere Market"},
    {"item": "Cooking Oil (1L)", "normal": 7500, "member": 6500, "seller": "Ntinda Wholesale"},
    {"item": "Bar Soap", "normal": 3500, "member": 2900, "seller": "Mutungo Trader"},
    {"item": "Charcoal (small sack)", "normal": 35000, "member": 30000, "seller": "Makindye Energy"},
    {"item": "Gas Refill (6kg)", "normal": 60000, "member": 55000, "seller": "Makindye Energy"},
    {"item": "Data 1GB", "normal": 5000, "member": 4200, "seller": "Verified Agent"},
    {"item": "Exercise Books (10pk)", "normal": 12000, "member": 9500, "seller": "Nansana School Supplies"},
    {"item": "Lunch (rice+beans+meat)", "normal": 9000, "member": 7500, "seller": "Mama Joy Kitchen"},
    {"item": "Diapers (medium pk)", "normal": 28000, "member": 24000, "seller": "Luzira Pharmacy"},
    {"item": "Sanitary pads (8pk)", "normal": 4500, "member": 3800, "seller": "Luzira Pharmacy"},
    {"item": "Phone charger (Type-C)", "normal": 15000, "member": 12000, "seller": "Nakawa Phone Shop"},
]

NEARBY_DEALS = [
    {"item": "2kg Sugar", "normal": 8400, "member": 7000, "seller": "Kitintale Mini Mart", "distance": "0.4km", "category": "Daily Basket", "stock": 18, "expires": "Today, 6:00 PM", "verified": True, "rating": 4.8},
    {"item": "Panadol Extra (24 tabs)", "normal": 6500, "member": 5200, "seller": "Luzira Pharmacy", "distance": "0.9km", "category": "Pharmacy", "stock": 32, "expires": "Tomorrow", "verified": True, "rating": 4.9},
    {"item": "Lunch (rice+beans+chicken)", "normal": 9000, "member": 7500, "seller": "Mama Joy Kitchen", "distance": "1.2km", "category": "Restaurants", "stock": 14, "expires": "Today, 3:00 PM", "verified": True, "rating": 4.7},
    {"item": "Geometry Set", "normal": 7500, "member": 5800, "seller": "Nansana School Supplies", "distance": "2.1km", "category": "School Items", "stock": 9, "expires": "3 days", "verified": True, "rating": 4.6},
    {"item": "Phone Charger (Type-C)", "normal": 15000, "member": 12000, "seller": "Nakawa Phone Shop", "distance": "1.8km", "category": "Phone & Data", "stock": 22, "expires": "1 week", "verified": True, "rating": 4.4},
    {"item": "Gas Refill (6kg)", "normal": 60000, "member": 55000, "seller": "Makindye Energy", "distance": "2.4km", "category": "Daily Basket", "stock": 6, "expires": "Today", "verified": True, "rating": 4.8},
]

CLAIMED_OFFERS = [
    {"item": "2kg Sugar", "code": "1K-7H2P", "seller": "Kitintale Mini Mart", "expires": "Today, 6:00 PM", "saving": 1400, "status": "active"},
    {"item": "Lunch combo", "code": "1K-K9X4", "seller": "Mama Joy Kitchen", "expires": "Today, 3:00 PM", "saving": 1500, "status": "active"},
    {"item": "Panadol Extra", "code": "1K-M3R7", "seller": "Luzira Pharmacy", "expires": "Yesterday", "saving": 1300, "status": "used"},
    {"item": "Charcoal sack", "code": "1K-Q8L1", "seller": "Makindye Energy", "expires": "2 days ago", "saving": 5000, "status": "expired"},
]

MEMBER_SAVINGS_HISTORY = [
    {"month": "May", "saved": 18400},
    {"month": "Jun", "saved": 22100},
    {"month": "Jul", "saved": 19800},
    {"month": "Aug", "saved": 27200},
    {"month": "Sep", "saved": 31500},
    {"month": "Oct", "saved": 24800},
]

MERCHANT_OFFERS = [
    {"item": "2kg Sugar", "normal": 8400, "member": 7000, "qty": 24, "expires": "Today", "views": 142, "claims": 18, "status": "Active"},
    {"item": "Maize Flour 5kg", "normal": 16000, "member": 13800, "qty": 10, "expires": "Tomorrow", "views": 96, "claims": 7, "status": "Active"},
    {"item": "Bar Soap (4pk)", "normal": 13800, "member": 11600, "qty": 30, "expires": "3 days", "views": 88, "claims": 11, "status": "Active"},
    {"item": "Cooking Oil 2L", "normal": 14500, "member": 12800, "qty": 12, "expires": "Today", "views": 64, "claims": 9, "status": "Paused"},
]

MERCHANT_CLAIMS = [
    {"code": "1K-7H2P", "member": "Sarah N.", "item": "2kg Sugar", "status": "Redeemed", "time": "10:42 AM"},
    {"code": "1K-K9X4", "member": "Brian K.", "item": "Lunch combo", "status": "Pending", "time": "11:08 AM"},
    {"code": "1K-M3R7", "member": "Aisha M.", "item": "Bar Soap (4pk)", "status": "Redeemed", "time": "11:25 AM"},
    {"code": "1K-Q8L1", "member": "Joseph S.", "item": "Cooking Oil 2L", "status": "Expired", "time": "Yesterday"},
]

RIDER_JOBS = [
    {"id": "JOB-2041", "from": "Kitintale Mini Mart", "to": "Mutungo Block C", "item": "2kg Sugar", "fare": 3000, "status": "On route"},
    {"id": "JOB-2039", "from": "Mama Joy Kitchen", "to": "Mutungo Stage", "item": "Lunch combo", "fare": 2500, "status": "Picked up"},
    {"id": "JOB-2035", "from": "Luzira Pharmacy", "to": "Mutungo Zone 4", "item": "Panadol Extra", "fare": 3500, "status": "Delivered"},
    {"id": "JOB-2032", "from": "Nakawa Phone Shop", "to": "Bugolobi", "item": "Type-C Charger", "fare": 4000, "status": "Delivered"},
]

RIDER_ROUTE_TODAY = {
    "routeName": "Mutungo → CBD",
    "packages": 12,
    "gross": 42000,
    "commission": 4200,
    "net": 37800,
}

CUSTOMER_FEEDBACK = [
    {"who": "Sarah N.", "rating": 5, "note": "Sugar was fresh and code worked instantly."},
    {"who": "Brian K.", "rating": 4, "note": "Good service, queue was a bit long."},
    {"who": "Aisha M.", "rating": 5, "note": "Soap was exactly the member price. Asante!"},
]

AGENT_MERCHANTS_TO_VERIFY = [
    {"name": "Nansana Pharmacy", "area": "Nansana", "category": "Pharmacy", "contact": "0772 xxx 112"},
    {"name": "Katabi Fresh Foods", "area": "Katabi", "category": "Daily Basket", "contact": "0701 xxx 884"},
    {"name": "Entebbe School Mart", "area": "Entebbe", "category": "School Items", "contact": "0758 xxx 220"},
]

AGENT_RIDERS_TO_VERIFY = [
    {"name": "Tonny Kato", "stage": "Nansana Stage", "area": "Nansana"},
    {"name": "Edward Otim", "stage": "Katabi Stage", "area": "Katabi"},
]

AGENT_PRICE_COLLECTION = [
    {"item": "Rice (1kg)", "lastPrice": 4500},
    {"item": "Sugar (1kg)", "lastPrice": 4200},
    {"item": "Beans (1kg)", "lastPrice": 3800},
    {"item": "Cooking Oil (1L)", "lastPrice": 7500},
    {"item": "Bar Soap", "lastPrice": 3500},
    {"item": "Charcoal (small sack)", "lastPrice": 35000},
    {"item": "Gas Refill (6kg)", "lastPrice": 60000},
    {"item": "Data 1GB", "lastPrice": 5000},
    {"item": "Exercise Books (10pk)", "lastPrice": 12000},
    {"item": "Lunch combo", "lastPrice": 9000},
]

# ===== Admin module datasets =====

ALL_MEMBERS = [
    {"name": "Sarah Nakato", "phone": "0772 411 220", "area": "Mutungo", "status": "Active", "renewal": "12 Nov", "saved": 24800, "possible": 31200, "claims": 12, "complaints": 0, "referrals": 3, "last": "2 min ago"},
    {"name": "Brian Kato", "phone": "0701 882 117", "area": "Ntinda", "status": "Active", "renewal": "20 Nov", "saved": 18200, "possible": 26500, "claims": 9, "complaints": 1, "referrals": 1, "last": "1 hr ago"},
    {"name": "Aisha Mukasa", "phone": "0758 220 991", "area": "Bweyogerere", "status": "Expired", "renewal": "5 Nov", "saved": 14200, "possible": 19800, "claims": 6, "complaints": 2, "referrals": 0, "last": "Yesterday"},
    {"name": "Joseph Ssempa", "phone": "0703 119 220", "area": "Kireka", "status": "Active", "renewal": "28 Nov", "saved": 21100, "possible": 28000, "claims": 11, "complaints": 0, "referrals": 2, "last": "3 hr ago"},
    {"name": "Grace Namukasa", "phone": "0782 555 102", "area": "Nansana", "status": "Active", "renewal": "15 Nov", "saved": 30200, "possible": 38400, "claims": 16, "complaints": 0, "referrals": 5, "last": "30 min ago"},
    {"name": "Patrick Okello", "phone": "0712 770 442", "area": "Nakawa", "status": "Suspended", "renewal": "—", "saved": 6800, "possible": 8100, "claims": 3, "complaints": 4, "referrals": 0, "last": "1 week ago"},
    {"name": "Doreen Atim", "phone": "0760 220 110", "area": "Luzira", "status": "Active", "renewal": "22 Nov", "saved": 19400, "possible": 24700, "claims": 8, "complaints": 0, "referrals": 2, "last": "5 hr ago"},
    {"name": "Henry Kiprotich", "phone": "0778 880 442", "area": "Katabi", "status": "Active", "renewal": "9 Nov", "saved": 11200, "possible": 15400, "claims": 5, "complaints": 0, "referrals": 1, "last": "1 day ago"},
]

SUBSCRIPTION_PLANS = [
    {"code": "1K-MONTHLY", "label": "Monthly", "price": 1000, "period": "month", "popular": True},
    {"code": "3K-QUARTERLY", "label": "Quarterly", "price": 3000, "period": "3 months", "popular": False},
    {"code": "6K-SEMI", "label": "Six Months", "price": 6000, "period": "6 months", "popular": False},
    {"code": "10K-YEAR", "label": "Yearly Promo", "price": 10000, "period": "year", "popular": True},
]

SUBSCRIPTION_ROWS = [
    {"member": "Sarah Nakato", "plan": "Monthly", "paid": 1000, "method": "MTN MoMo", "reference": "MOMO-7H2P", "status": "Active", "renewal": "12 Nov"},
    {"member": "Brian Kato", "plan": "Monthly", "paid": 1000, "method": "Airtel Money", "reference": "AM-K9X4", "status": "Active", "renewal": "20 Nov"},
    {"member": "Grace Namukasa", "plan": "Quarterly", "paid": 3000, "method": "MTN MoMo", "reference": "MOMO-M3R7", "status": "Active", "renewal": "15 Jan"},
    {"member": "Aisha Mukasa", "plan": "Monthly", "paid": 1000, "method": "MTN MoMo", "reference": "MOMO-Q8L1", "status": "Failed", "renewal": "—"},
    {"member": "Henry Kiprotich", "plan": "Yearly Promo", "paid": 10000, "method": "Airtel Money", "reference": "AM-N4P2", "status": "Active", "renewal": "9 Sep 2026"},
]

ALL_MERCHANTS = [
    {"name": "Kitintale Mini Mart", "area": "Kitintale", "category": "Daily Basket", "status": "Verified", "rating": 4.8, "accept": 96, "complaints": 1, "redemptions": 482, "sales": 5_400_000, "agent": "Agent Wakiso"},
    {"name": "Luzira Pharmacy", "area": "Luzira", "category": "Pharmacy", "status": "Verified", "rating": 4.9, "accept": 98, "complaints": 0, "redemptions": 312, "sales": 3_120_000, "agent": "Agent Mubiru"},
    {"name": "Mama Joy Kitchen", "area": "Mutungo", "category": "Restaurants", "status": "Verified", "rating": 4.7, "accept": 94, "complaints": 2, "redemptions": 268, "sales": 2_010_000, "agent": "Agent Wakiso"},
    {"name": "Nansana Pharmacy", "area": "Nansana", "category": "Pharmacy", "status": "Pending", "rating": 0, "accept": 0, "complaints": 0, "redemptions": 0, "sales": 0, "agent": "—"},
    {"name": "Bweyogerere Fresh Market", "area": "Bweyogerere", "category": "Daily Basket", "status": "Pending", "rating": 0, "accept": 0, "complaints": 0, "redemptions": 0, "sales": 0, "agent": "—"},
    {"name": "Nakawa Phone Shop", "area": "Nakawa", "category": "Phone & Data", "status": "Verified", "rating": 4.4, "accept": 88, "complaints": 3, "redemptions": 188, "sales": 2_640_000, "agent": "Agent Mubiru"},
    {"name": "Makindye Energy", "area": "Makindye", "category": "Daily Basket", "status": "Verified", "rating": 4.8, "accept": 95, "complaints": 1, "redemptions": 144, "sales": 8_640_000, "agent": "Agent Mubiru"},
    {"name": "Nansana School Supplies", "area": "Nansana", "category": "School Items", "status": "Verified", "rating": 4.6, "accept": 91, "complaints": 1, "redemptions": 96, "sales": 1_120_000, "agent": "Agent Wakiso"},
]

ALL_OFFERS = [
    {"item": "2kg Sugar", "merchant": "Kitintale Mini Mart", "category": "Daily Basket", "normal": 8400, "member": 7000, "stock": 18, "area": "Kitintale", "expires": "Today 6:00 PM", "status": "Active"},
    {"item": "Panadol Extra (24 tabs)", "merchant": "Luzira Pharmacy", "category": "Pharmacy", "normal": 6500, "member": 5200, "stock": 32, "area": "Luzira", "expires": "Tomorrow", "status": "Active"},
    {"item": "Lunch combo", "merchant": "Mama Joy Kitchen", "category": "Restaurants", "normal": 9000, "member": 7500, "stock": 14, "area": "Mutungo", "expires": "Today 3:00 PM", "status": "Active"},
    {"item": "5L Cooking Oil", "merchant": "Ntinda Wholesale", "category": "Daily Basket", "normal": 28000, "member": 24500, "stock": 8, "area": "Ntinda", "expires": "3 days", "status": "Pending"},
    {"item": "Geometry Set", "merchant": "Nansana School Supplies", "category": "School Items", "normal": 7500, "member": 5800, "stock": 9, "area": "Nansana", "expires": "5 days", "status": "Active"},
    {"item": "Type-C Charger", "merchant": "Nakawa Phone Shop", "category": "Phone & Data", "normal": 15000, "member": 12000, "stock": 22, "area": "Nakawa", "expires": "1 week", "status": "Active"},
    {"item": "Charcoal sack (M)", "merchant": "Makindye Energy", "category": "Daily Basket", "normal": 65000, "member": 58000, "stock": 6, "area": "Makindye", "expires": "2 days", "status": "Paused"},
    {"item": "Cheap Data 10GB", "merchant": "Unknown agent", "category": "Phone & Data", "normal": 30000, "member": 5000, "stock": 999, "area": "Kampala", "expires": "Today", "status": "Reported"},
]

CLAIM_CODES = [
    {"code": "1K-7H2P", "member": "Sarah N.", "merchant": "Kitintale Mini Mart", "item": "2kg Sugar", "saving": 1400, "expires": "Today 6:00 PM", "status": "Active"},
    {"code": "1K-K9X4", "member": "Brian K.", "merchant": "Mama Joy Kitchen", "item": "Lunch combo", "saving": 1500, "expires": "Today 3:00 PM", "status": "Active"},
    {"code": "1K-M3R7", "member": "Aisha M.", "merchant": "Luzira Pharmacy", "item": "Panadol Extra", "saving": 1300, "expires": "Used 11:25 AM", "status": "Used"},
    {"code": "1K-Q8L1", "member": "Joseph S.", "merchant": "Makindye Energy", "item": "Charcoal sack", "saving": 5000, "expires": "Yesterday", "status": "Expired"},
    {"code": "1K-N4P2", "member": "Grace N.", "merchant": "Nakawa Phone Shop", "item": "Type-C Charger", "saving": 3000, "expires": "Refused", "status": "Failed"},
    {"code": "1K-XR99", "member": "Patrick O.", "merchant": "Kitintale Mini Mart", "item": "2kg Sugar", "saving": 1400, "expires": "6 attempts", "status": "Suspicious"},
]

ALL_RIDERS = [
    {"name": "Boda Musoke", "phone": "0772 110 220", "stage": "Mutungo Stage", "area": "Mutungo", "status": "Verified", "services": ["Nearby", "Shared route", "Returning trip"], "jobs": 482, "failed": 4, "rating": 4.8, "routeEarn": 480_000, "commPaid": 38_000, "commPending": 10_000},
    {"name": "Tonny Kato", "phone": "0701 220 110", "stage": "Nansana Stage", "area": "Nansana", "status": "Pending", "services": ["Nearby"], "jobs": 0, "failed": 0, "rating": 0, "routeEarn": 0, "commPaid": 0, "commPending": 0},
    {"name": "Edward Otim", "phone": "0758 442 119", "stage": "Katabi Stage", "area": "Katabi", "status": "Pending", "services": ["Nearby", "Shared route"], "jobs": 0, "failed": 0, "rating": 0, "routeEarn": 0, "commPaid": 0, "commPending": 0},
    {"name": "Patrick Okello", "phone": "0712 882 119", "stage": "Kireka Stage", "area": "Kireka", "status": "Verified", "services": ["Nearby", "Shared route"], "jobs": 244, "failed": 8, "rating": 4.2, "routeEarn": 220_000, "commPaid": 18_000, "commPending": 4_000},
    {"name": "Joseph Ssempa", "phone": "0703 119 882", "stage": "Mutungo Stage", "area": "Mutungo", "status": "Pending", "services": ["Nearby"], "jobs": 0, "failed": 0, "rating": 0, "routeEarn": 0, "commPaid": 0, "commPending": 0},
    {"name": "Henry Mukisa", "phone": "0782 220 110", "stage": "Bweyogerere Stage", "area": "Bweyogerere", "status": "Verified", "services": ["Nearby", "Shared route", "Returning trip"], "jobs": 312, "failed": 2, "rating": 4.7, "routeEarn": 290_000, "commPaid": 22_000, "commPending": 7_000},
]

ROUTE_DELIVERIES = [
    {"name": "Mutungo → CBD", "from": "Mutungo", "to": "Kitintale → Luzira → CBD", "dispatch": "07:30", "rider": "Boda Musoke", "packages": 12, "earnings": 42_000, "commission": 4_200, "status": "In progress"},
    {"name": "Kireka → Nakawa", "from": "Kireka", "to": "Bweyogerere → Namugongo", "dispatch": "08:00", "rider": "Patrick Okello", "packages": 9, "earnings": 28_000, "commission": 2_800, "status": "Completed"},
    {"name": "Nansana → Kampala", "from": "Nansana", "to": "Kampala", "dispatch": "09:00", "rider": "Henry Mukisa", "packages": 14, "earnings": 51_000, "commission": 5_100, "status": "Loading"},
    {"name": "Katabi → Entebbe", "from": "Katabi", "to": "Entebbe", "dispatch": "10:30", "rider": "—", "packages": 6, "earnings": 0, "commission": 0, "status": "Scheduled"},
    {"name": "Kampala → Makindye", "from": "Kampala", "to": "Makindye", "dispatch": "Yesterday", "rider": "Boda Musoke", "packages": 8, "earnings": 24_000, "commission": 2_400, "status": "Failed"},
]

PICKUP_POINTS = [
    {"name": "Mutungo Stage Kiosk", "area": "Mutungo", "owner": "James M.", "type": "Mobile money kiosk", "status": "Active", "received": 142, "collected": 138, "complaints": 1, "agent": "Agent Wakiso"},
    {"name": "Kitintale Salon Hub", "area": "Kitintale", "owner": "Sandra B.", "type": "Salon", "status": "Active", "received": 88, "collected": 84, "complaints": 0, "agent": "Agent Wakiso"},
    {"name": "Bweyogerere Stationery", "area": "Bweyogerere", "owner": "Joseph N.", "type": "Stationery shop", "status": "Active", "received": 64, "collected": 60, "complaints": 1, "agent": "Agent Mubiru"},
    {"name": "Nansana Mini Supermarket", "area": "Nansana", "owner": "Doreen K.", "type": "Mini supermarket", "status": "Pending", "received": 0, "collected": 0, "complaints": 0, "agent": "Agent Wakiso"},
    {"name": "Entebbe Pharmacy Drop", "area": "Entebbe", "owner": "Grace L.", "type": "Pharmacy", "status": "Active", "received": 42, "collected": 40, "complaints": 0, "agent": "Agent Wakiso"},
    {"name": "Kireka Boda Stage", "area": "Kireka", "owner": "Stage Chair", "type": "Boda stage", "status": "Suspended", "received": 28, "collected": 22, "complaints": 4, "agent": "Agent Mubiru"},
]

AGENT_ROLES = ["Field agent", "Supervisor agent", "Price collector", "Complaint investigator", "Merchant/rider verifier"]

PERMISSIONS = [
    "Verify merchants", "Verify riders", "Collect prices", "Investigate complaints",
    "Approve directly", "Recommend approval only", "View earnings", "Access multiple areas",
]

ALL_AGENTS = [
    {"name": "Agent Wakiso", "phone": "0772 880 110", "areas": ["Nansana", "Katabi", "Entebbe"], "role": "Field agent", "status": "Active", "merchants": 48, "riders": 22, "prices": 412, "complaints": 18, "earnings": 248_000, "last": "10 min ago"},
    {"name": "Agent Mubiru", "phone": "0701 119 220", "areas": ["Kireka", "Bweyogerere"], "role": "Supervisor agent", "status": "Active", "merchants": 64, "riders": 31, "prices": 502, "complaints": 24, "earnings": 322_000, "last": "1 hr ago"},
    {"name": "Agent Nakimera", "phone": "0758 220 778", "areas": ["Mutungo", "Kitintale", "Luzira"], "role": "Field agent", "status": "Active", "merchants": 38, "riders": 18, "prices": 380, "complaints": 12, "earnings": 196_000, "last": "32 min ago"},
    {"name": "Agent Tumusiime", "phone": "0703 442 110", "areas": ["Ntinda", "Nakawa"], "role": "Price collector", "status": "Pending", "merchants": 0, "riders": 0, "prices": 0, "complaints": 0, "earnings": 0, "last": "—"},
    {"name": "Agent Lubega", "phone": "0782 110 998", "areas": ["Makindye"], "role": "Complaint investigator", "status": "Suspended", "merchants": 12, "riders": 4, "prices": 120, "complaints": 38, "earnings": 80_000, "last": "1 week ago"},
]

AGENT_TASKS = [
    {"task": "Verify Nansana Pharmacy", "type": "Merchant verification", "agent": "Agent Wakiso", "area": "Nansana", "priority": "High", "due": "Today", "status": "In progress"},
    {"task": "Verify Tonny Kato (rider)", "type": "Rider verification", "agent": "Agent Wakiso", "area": "Nansana", "priority": "Medium", "due": "Today", "status": "Pending"},
    {"task": "Collect basket prices", "type": "Price collection", "agent": "Agent Mubiru", "area": "Bweyogerere", "priority": "High", "due": "Today", "status": "In progress"},
    {"task": "Investigate fake deal “10GB @ 5K”", "type": "Complaint investigation", "agent": "Agent Mubiru", "area": "Kampala", "priority": "High", "due": "Today", "status": "Escalated"},
    {"task": "Inspect Kireka Boda Stage pickup", "type": "Pickup point inspection", "agent": "Agent Mubiru", "area": "Kireka", "priority": "Medium", "due": "Tomorrow", "status": "Pending"},
    {"task": "Re-verify Nakawa Phone Shop codes", "type": "Merchant verification", "agent": "Agent Nakimera", "area": "Nakawa", "priority": "High", "due": "Today", "status": "Pending"},
    {"task": "Area inspection — Entebbe", "type": "Area inspection", "agent": "Agent Wakiso", "area": "Entebbe", "priority": "Low", "due": "This week", "status": "Pending"},
]

PRICE_DATABASE = [
    {"item": "Rice (1kg)", "area": "Mutungo", "current": 4500, "previous": 4400, "low": 4200, "high": 4800, "agent": "Agent Nakimera", "date": "Today"},
    {"item": "Sugar (1kg)", "area": "Kitintale", "current": 4200, "previous": 4300, "low": 4000, "high": 4500, "agent": "Agent Nakimera", "date": "Today"},
    {"item": "Beans (1kg)", "area": "Bweyogerere", "current": 3800, "previous": 3700, "low": 3600, "high": 4000, "agent": "Agent Mubiru", "date": "Today"},
    {"item": "Cooking Oil (1L)", "area": "Ntinda", "current": 7500, "previous": 7800, "low": 7200, "high": 8200, "agent": "Agent Tumusiime", "date": "Yesterday"},
    {"item": "Charcoal (sack)", "area": "Makindye", "current": 35000, "previous": 36000, "low": 32000, "high": 38000, "agent": "Agent Lubega", "date": "Today"},
    {"item": "Gas Refill (6kg)", "area": "Makindye", "current": 60000, "previous": 60000, "low": 58000, "high": 62000, "agent": "Agent Lubega", "date": "Today"},
    {"item": "Data 1GB", "area": "Kampala", "current": 5000, "previous": 5000, "low": 4500, "high": 5500, "agent": "Agent Mubiru", "date": "Today"},
    {"item": "Lunch combo", "area": "Mutungo", "current": 9000, "previous": 8500, "low": 7500, "high": 10000, "agent": "Agent Nakimera", "date": "Today"},
]

PAYMENTS = [
    {"ref": "MOMO-7H2P", "who": "Sarah Nakato", "type": "Subscription", "amount": 1000, "method": "MTN MoMo", "status": "Success", "time": "10:42 AM"},
    {"ref": "MOMO-K9X4", "who": "Brian Kato", "type": "Subscription", "amount": 1000, "method": "MTN MoMo", "status": "Success", "time": "10:51 AM"},
    {"ref": "AM-M3R7", "who": "Grace Namukasa", "type": "Subscription", "amount": 3000, "method": "Airtel Money", "status": "Success", "time": "11:08 AM"},
    {"ref": "MOMO-Q8L1", "who": "Aisha Mukasa", "type": "Subscription", "amount": 1000, "method": "MTN MoMo", "status": "Failed", "time": "11:25 AM"},
    {"ref": "MOMO-P82B", "who": "Mama Joy Kitchen", "type": "Spotlight Day", "amount": 25000, "method": "MTN MoMo", "status": "Success", "time": "Yesterday"},
    {"ref": "AM-V44H", "who": "Henry Kiprotich", "type": "Subscription", "amount": 10000, "method": "Airtel Money", "status": "Success", "time": "Yesterday"},
]

SETTLEMENTS = [
    {"who": "Boda Musoke", "type": "Route commission", "gross": 480_000, "commission": 48_000, "net": 432_000, "paid": 422_000, "pending": 10_000, "period": "Oct"},
    {"who": "Patrick Okello", "type": "Route commission", "gross": 220_000, "commission": 22_000, "net": 198_000, "paid": 194_000, "pending": 4_000, "period": "Oct"},
    {"who": "Henry Mukisa", "type": "Route commission", "gross": 290_000, "commission": 29_000, "net": 261_000, "paid": 254_000, "pending": 7_000, "period": "Oct"},
    {"who": "Agent Wakiso", "type": "Agent payout", "gross": 248_000, "commission": 0, "net": 248_000, "paid": 200_000, "pending": 48_000, "period": "Oct"},
    {"who": "Agent Mubiru", "type": "Agent payout", "gross": 322_000, "commission": 0, "net": 322_000, "paid": 280_000, "pending": 42_000, "period": "Oct"},
]

COMPLAINTS = [
    {"id": "CMP-1042", "member": "Aisha M.", "target": "Nakawa Phone Shop", "type": "Code refused", "area": "Nakawa", "priority": "High", "agent": "Agent Mubiru", "sla": "2 hr left", "status": "Investigating"},
    {"id": "CMP-1041", "member": "Brian K.", "target": "Unknown agent", "type": "Fake deal", "area": "Kampala", "priority": "High", "agent": "Agent Mubiru", "sla": "Overdue", "status": "Escalated"},
    {"id": "CMP-1040", "member": "Doreen A.", "target": "Boda Patrick", "type": "Failed delivery", "area": "Kireka", "priority": "Medium", "agent": "Agent Mubiru", "sla": "1 day left", "status": "Waiting rider"},
    {"id": "CMP-1039", "member": "Grace N.", "target": "Kitintale Mini Mart", "type": "Wrong price", "area": "Kitintale", "priority": "Medium", "agent": "Agent Nakimera", "sla": "6 hr left", "status": "Investigating"},
    {"id": "CMP-1038", "member": "Henry K.", "target": "Kireka Boda Stage", "type": "Pickup point issue", "area": "Kireka", "priority": "High", "agent": "Agent Mubiru", "sla": "Overdue", "status": "Waiting agent"},
    {"id": "CMP-1037", "member": "Joseph S.", "target": "Makindye Energy", "type": "Item unavailable", "area": "Makindye", "priority": "Low", "agent": "Agent Lubega", "sla": "Resolved", "status": "Resolved"},
]

CAMPAIGNS = [
    {"name": "October renewal reminder", "channel": "SMS", "audience": "Expiring this week", "area": "All", "status": "Sent", "sent": 1240, "failed": 18, "schedule": "Today 9:00 AM"},
    {"name": "Weekend basket deals", "channel": "In-app", "audience": "All members", "area": "Kampala", "status": "Scheduled", "sent": 0, "failed": 0, "schedule": "Fri 6:00 PM"},
    {"name": "Price drop: Sugar", "channel": "WhatsApp", "audience": "Kitintale & Mutungo", "area": "Kitintale, Mutungo", "status": "Sent", "sent": 480, "failed": 4, "schedule": "Yesterday"},
    {"name": "Route launch: Nansana → CBD", "channel": "SMS", "audience": "Nansana members", "area": "Nansana", "status": "Draft", "sent": 0, "failed": 0, "schedule": "—"},
]

# ===== Nakawa East launch focus + community marketplace datasets =====

LAUNCH_AREAS = ["Mutungo", "Kitintale", "Luzira", "Mbuya II", "Kirombe", "Bugolobi"]

COMPARE_SOAP_NEARBY = [
    {"seller": "Mutungo Trader", "area": "Mutungo", "distance": "0.3km", "normal": 3500, "member": 2800, "stock": 42, "expires": "Today 7 PM", "badges": ["Verified today", "Best price nearby"]},
    {"seller": "Kitintale Mini Mart", "area": "Kitintale", "distance": "0.8km", "normal": 3500, "member": 2950, "stock": 60, "expires": "Tomorrow", "badges": ["Verified", "Delivery available"]},
    {"seller": "Luzira Corner Shop", "area": "Luzira", "distance": "1.4km", "normal": 3500, "member": 3000, "stock": 18, "expires": "Today", "badges": ["Agent checked"]},
    {"seller": "Mbuya II Vendor Joy", "area": "Mbuya II", "distance": "1.9km", "normal": 3500, "member": 3100, "stock": 9, "expires": "Today 5 PM", "badges": ["Limited stock"]},
    {"seller": "Bugolobi Pharmacy", "area": "Bugolobi", "distance": "2.6km", "normal": 3500, "member": 3200, "stock": 24, "expires": "3 days", "badges": ["Verified"]},
]

SEARCH_CATEGORIES = [
    {"key": "soap", "label": "Soap", "emoji": "🧼"},
    {"key": "rice", "label": "Rice", "emoji": "🍚"},
    {"key": "posho", "label": "Posho", "emoji": "🌽"},
    {"key": "sugar", "label": "Sugar", "emoji": "🍬"},
    {"key": "oil", "label": "Cooking Oil", "emoji": "🛢️"},
    {"key": "vegetables", "label": "Vegetables", "emoji": "🥬"},
    {"key": "fruits", "label": "Fruits", "emoji": "🍌"},
    {"key": "pharmacy", "label": "Pharmacy", "emoji": "💊"},
    {"key": "food", "label": "Food / Lunch", "emoji": "🍛"},
    {"key": "school", "label": "School Items", "emoji": "📚"},
    {"key": "gas", "label": "Gas", "emoji": "🔥"},
    {"key": "charcoal", "label": "Charcoal", "emoji": "🪵"},
    {"key": "phone", "label": "Phone & Data", "emoji": "📱"},
]

LIVE_LOCAL_DEALS = [
    {"item": "Posho (1kg)", "seller": "Kirombe Vendor Hub", "vendorType": "Market vendor", "area": "Kirombe", "distance": "0.5km", "normal": 3000, "member": 2500, "stock": 30, "expires": "Today 6 PM", "emoji": "🌽", "badges": ["Best on posho today", "Verified today"], "delivery": True},
    {"item": "Tomatoes (basin)", "seller": "Mama Sanyu Fresh", "vendorType": "Fruit & veg", "area": "Mutungo", "distance": "0.4km", "normal": 12000, "member": 9500, "stock": 14, "expires": "Today", "emoji": "🍅", "badges": ["Fresh today", "Limited stock"], "delivery": True},
    {"item": "Rice (5kg)", "seller": "Kitintale Mini Mart", "vendorType": "Retail shop", "area": "Kitintale", "distance": "0.9km", "normal": 22000, "member": 19000, "stock": 18, "expires": "Tomorrow", "emoji": "🍚", "badges": ["Best on rice today", "Agent checked"], "delivery": True},
    {"item": "Bar Soap (4pk)", "seller": "Luzira Corner Shop", "vendorType": "Retail shop", "area": "Luzira", "distance": "1.2km", "normal": 13800, "member": 11600, "stock": 22, "expires": "3 days", "emoji": "🧼", "badges": ["Best on soap today"], "delivery": True},
    {"item": "Lunch combo", "seller": "Mama Joy Kitchen", "vendorType": "Restaurant", "area": "Mutungo", "distance": "0.6km", "normal": 9000, "member": 7500, "stock": 14, "expires": "Today 3 PM", "emoji": "🍛", "badges": ["Lunch offer today", "Verified"], "delivery": True},
    {"item": "Sugar (2kg)", "seller": "Mbuya II Vendor Joy", "vendorType": "Home seller", "area": "Mbuya II", "distance": "1.6km", "normal": 8400, "member": 7000, "stock": 12, "expires": "Today", "emoji": "🍬", "badges": ["Nearby", "Limited stock"], "delivery": False},
    {"item": "Panadol Extra", "seller": "Bugolobi Pharmacy", "vendorType": "Pharmacy", "area": "Bugolobi", "distance": "2.1km", "normal": 6500, "member": 5200, "stock": 32, "expires": "Tomorrow", "emoji": "💊", "badges": ["Pharmacy essentials today", "Verified"], "delivery": True},
    {"item": "Exercise Books 10pk", "seller": "Kirombe School Mart", "vendorType": "School items", "area": "Kirombe", "distance": "1.0km", "normal": 12000, "member": 9500, "stock": 9, "expires": "5 days", "emoji": "📚", "badges": ["Agent checked"], "delivery": True},
    {"item": "Charcoal (sack)", "seller": "Luzira Energy", "vendorType": "Home seller", "area": "Luzira", "distance": "1.8km", "normal": 35000, "member": 30000, "stock": 6, "expires": "Today", "emoji": "🪵", "badges": ["Best price nearby"], "delivery": True},
    {"item": "Cooking Oil (2L)", "seller": "Kitintale Wholesale", "vendorType": "Wholesale", "area": "Kitintale", "distance": "0.7km", "normal": 14500, "member": 12800, "stock": 10, "expires": "Today", "emoji": "🛢️", "badges": ["Verified"], "delivery": True},
]

MEMBER_REQUESTS = [
    {"item": "Posho (5kg)", "who": "Sarah N.", "area": "Mutungo", "when": "8 min ago", "responses": 0},
    {"item": "Sukuma wiki bundle", "who": "Brian K.", "area": "Bugolobi", "when": "22 min ago", "responses": 2},
    {"item": "Diapers medium pk", "who": "Aisha M.", "area": "Kitintale", "when": "1 hr ago", "responses": 1},
    {"item": "School uniform (P3)", "who": "Grace N.", "area": "Luzira", "when": "2 hr ago", "responses": 0},
    {"item": "Cooking gas (6kg)", "who": "Henry K.", "area": "Mbuya II", "when": "3 hr ago", "responses": 4},
]

SUPPLY_GAPS = [
    {"item": "Posho (5kg)", "area": "Mutungo", "searches": 142, "offers": 0, "lastOffer": "11 days ago"},
    {"item": "Sukuma wiki bundle", "area": "Bugolobi", "searches": 96, "offers": 1, "lastOffer": "Today"},
    {"item": "Baby formula", "area": "Kitintale", "searches": 84, "offers": 0, "lastOffer": "Never"},
    {"item": "School shoes (sz 32)", "area": "Kirombe", "searches": 62, "offers": 0, "lastOffer": "30+ days"},
    {"item": "Fresh milk 1L", "area": "Luzira", "searches": 58, "offers": 0, "lastOffer": "5 days ago"},
    {"item": "Charcoal (full sack)", "area": "Mbuya II", "searches": 44, "offers": 1, "lastOffer": "Today"},
]

PRICE_MOVEMENTS = [
    {"item": "Sugar (1kg)", "area": "Kitintale", "from": 4300, "to": 4200, "change": -2.3, "direction": "down"},
    {"item": "Posho (1kg)", "area": "Kirombe", "from": 2700, "to": 2500, "change": -7.4, "direction": "down"},
    {"item": "Tomatoes/basin", "area": "Mutungo", "from": 10000, "to": 12000, "change": 20, "direction": "up"},
    {"item": "Charcoal sack", "area": "Luzira", "from": 32000, "to": 30000, "change": -6.3, "direction": "down"},
    {"item": "Cooking Oil 1L", "area": "Bugolobi", "from": 7200, "to": 7500, "change": 4.2, "direction": "up"},
    {"item": "Rice (1kg)", "area": "Mbuya II", "from": 4600, "to": 4500, "change": -2.2, "direction": "down"},
]

MERCHANT_STRENGTH_MAP = [
    {"area": "Mutungo", "bestOn": ["Tomatoes", "Lunch combos", "Fresh produce"]},
    {"area": "Kitintale", "bestOn": ["Rice", "Sugar", "Cooking oil"]},
    {"area": "Luzira", "bestOn": ["Charcoal", "Soap"]},
    {"area": "Mbuya II", "bestOn": ["Home-made foods", "Fruits"]},
    {"area": "Kirombe", "bestOn": ["Posho", "School items"]},
    {"area": "Bugolobi", "bestOn": ["Pharmacy", "Cleaning supplies"]},
]

AREA_LAUNCH_PROGRESS = [
    {"area": "Mutungo", "stage": "Live", "members": 1240, "merchants": 38, "riders": 14, "agents": 2, "coverage": 92, "opened": "Apr 2026"},
    {"area": "Kitintale", "stage": "Live", "members": 1080, "merchants": 32, "riders": 12, "agents": 2, "coverage": 88, "opened": "Apr 2026"},
    {"area": "Luzira", "stage": "Live", "members": 860, "merchants": 24, "riders": 9, "agents": 1, "coverage": 78, "opened": "May 2026"},
    {"area": "Mbuya II", "stage": "Soft launch", "members": 410, "merchants": 14, "riders": 6, "agents": 1, "coverage": 54, "opened": "May 2026"},
    {"area": "Kirombe", "stage": "Soft launch", "members": 320, "merchants": 11, "riders": 5, "agents": 1, "coverage": 48, "opened": "May 2026"},
    {"area": "Bugolobi", "stage": "Pilot", "members": 220, "merchants": 18, "riders": 7, "agents": 1, "coverage": 40, "opened": "May 2026"},
]

STRENGTH_TAGS = [
    "Best on rice today", "Best on posho today", "Best on soap today",
    "Fresh vegetables today", "Lunch offers today", "Pharmacy essentials today",
    "Cheapest charcoal today", "Phone & data deals",
]

VENDOR_TYPES = [
    "Retail shop", "Restaurant", "Pharmacy", "Salon",
    "Market vendor", "Fruit & vegetable", "Home-based seller",
    "School items seller", "Phone & data seller", "Small wholesaler",
]

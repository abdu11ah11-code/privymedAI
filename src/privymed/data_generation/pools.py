"""Curated value pools. Tuples (not sets) so iteration order is deterministic."""

from __future__ import annotations

PK_MALE_FIRST: tuple[str, ...] = (
    "Ahmed", "Ali", "Usman", "Bilal", "Hamza", "Hassan", "Hussain", "Imran", "Kamran", "Faisal",
    "Asad", "Saad", "Zain", "Umar", "Abdullah", "Ibrahim", "Junaid", "Waqas", "Tariq", "Shahid",
    "Naveed", "Adnan", "Farhan", "Rizwan", "Salman", "Danish", "Arslan", "Haris", "Talha", "Zubair",
    "Owais", "Fahad", "Shoaib", "Azhar", "Nadeem", "Sajid", "Khalid", "Rashid", "Yasir", "Aamir",
    "Muneeb", "Taimur", "Moiz", "Ammar", "Ehsan", "Ghulam", "Iftikhar", "Jawad", "Mudassir", "Qasim",
    "Rehan", "Sohail", "Tahir", "Waseem", "Zeeshan", "Babar", "Daud", "Fawad", "Haider", "Noman",
)  # fmt: skip

PK_FEMALE_FIRST: tuple[str, ...] = (
    "Ayesha", "Fatima", "Zainab", "Maryam", "Hira", "Sana", "Amna", "Iqra", "Mahnoor", "Areeba",
    "Sadia", "Nadia", "Rabia", "Saima", "Huma", "Bushra", "Farah", "Kiran", "Mehwish", "Sobia",
    "Anam", "Aleena", "Khadija", "Laiba", "Noor", "Rida", "Sidra", "Tayyaba", "Uzma", "Zara",
    "Asma", "Shazia", "Nimra", "Hafsa", "Javeria", "Komal", "Lubna", "Misbah", "Naila", "Parveen",
    "Rukhsana", "Samina", "Tahira", "Yasmin", "Zoya", "Aiman", "Benish", "Dua", "Eman", "Ghazala",
    "Hina", "Irum", "Mehreen", "Nazia", "Qurat", "Rimsha", "Shabana", "Tooba", "Unaiza", "Warda",
)  # fmt: skip

PK_SURNAMES: tuple[str, ...] = (
    "Khan", "Ahmed", "Ali", "Malik", "Butt", "Chaudhry", "Qureshi", "Sheikh", "Siddiqui", "Raza",
    "Hussain", "Iqbal", "Javed", "Mirza", "Abbasi", "Awan", "Baig", "Bhatti", "Durrani", "Farooqi",
    "Gillani", "Hashmi", "Jamil", "Kazmi", "Khattak", "Lodhi", "Memon", "Mughal", "Niazi", "Rana",
    "Rehman", "Shah", "Soomro", "Tariq", "Usmani", "Warraich", "Yousaf", "Zaidi", "Afridi", "Ansari",
    "Bukhari", "Dar", "Ghani", "Jatoi", "Kiani", "Leghari", "Mahmood", "Nawaz", "Paracha", "Rizvi",
    "Saleem", "Sethi", "Talpur", "Wattoo", "Yusufzai", "Zafar", "Bajwa", "Cheema", "Gondal", "Tiwana",
)  # fmt: skip

# Faker locales for international names (first_name_*/last_name only).
INTL_LOCALES: tuple[str, ...] = (
    "en_US", "en_GB", "en_IN", "en_NG", "en_AU", "en_IE", "en_PH", "en_CA",
)  # fmt: skip

# Pakistani cities with plausible landline area codes and localities.
PK_CITIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Lahore", "042", ("Model Town", "Gulberg III", "Johar Town", "DHA Phase 5", "Iqbal Town",
                       "Faisal Town", "Wapda Town", "Samanabad", "Township", "Garden Town")),
    ("Karachi", "021", ("Gulshan-e-Iqbal", "North Nazimabad", "Clifton", "PECHS", "Malir",
                        "Korangi", "Gulistan-e-Jauhar", "Saddar", "Defence View", "Nazimabad")),
    ("Islamabad", "051", ("G-9/3", "F-7/2", "I-8/4", "G-11/1", "E-11", "F-10/1", "G-6/4",
                          "Bahria Enclave", "PWD Colony", "B-17")),
    ("Rawalpindi", "051", ("Satellite Town", "Saddar", "Chaklala Scheme III", "Westridge",
                           "Adiala Road", "Bahria Town Phase 4")),
    ("Peshawar", "091", ("Hayatabad Phase 3", "University Town", "Gulbahar", "Board Bazar",
                         "Regi Model Town")),
    ("Quetta", "081", ("Jinnah Town", "Samungli Road", "Satellite Town", "Brewery Road")),
    ("Multan", "061", ("Gulgasht Colony", "Shah Rukn-e-Alam Colony", "Cantt", "Bosan Road")),
    ("Faisalabad", "041", ("Peoples Colony", "Madina Town", "Susan Road", "Gulberg")),
    ("Hyderabad", "022", ("Latifabad Unit 7", "Qasimabad", "Hirabad", "Autobahn Road")),
    ("Sialkot", "052", ("Cantt", "Model Town", "Pasrur Road")),
    ("Gujranwala", "055", ("Satellite Town", "Model Town", "DC Colony")),
    ("Abbottabad", "0992", ("Jinnahabad", "Mandian", "Kaghan Colony")),
)  # fmt: skip

# Must be disjoint from HOSPITAL_CORES (tested): a hospital core appearing inside a train
# ADDRESS would leak an eval-split hospital string into train (review finding M2-7).
PK_BUILDING_WORDS: tuple[str, ...] = (
    "Gulzar", "Falak", "Shadab", "Kohinoor", "Shalimar", "Bahar", "Gulistan", "Faran",
    "Anarkali", "Kausar", "Firdous", "Shabnam",
)  # fmt: skip

PK_MOBILE_PREFIXES: tuple[str, ...] = (
    "300", "301", "302", "303", "304", "305", "306", "307", "308", "309", "310", "311", "312",
    "313", "314", "315", "320", "321", "322", "323", "330", "331", "332", "333", "334", "335",
    "336", "340", "341", "342", "343", "344", "345", "346", "347", "355",
)  # fmt: skip

# Fictional hospital-name parts. Combined at random; checked against a blocklist.
HOSPITAL_CORES: tuple[str, ...] = (
    "Crescent", "Evergreen", "Al-Noor", "Hayat", "Rehmat", "Sunrise", "Greenfield", "Silver Oak",
    "Northgate", "Sapphire", "Unity", "Hilal", "Sitara", "Riverside", "Cedar Hill", "Bright Path",
    "Zarghoon", "Margalla View", "Indus Valley", "Lakeside", "Noor-ul-Huda", "Gulnar Care",
    "Saint Brendan", "Westbrook", "Harbour", "Maple Grove", "Kohsar", "Mehran",
    "Bluebell", "Ravi View", "Pine Ridge", "Tulip", "Starling", "Chenab", "Oakwood",
    "Silver Crest", "Meadowbank", "Nishat Care", "Sunflower", "Summit", "Highgate",
    "Jhelum Valley", "Willowdale", "Shifa-e-Noor", "Rosewood Park", "Kingsbridge",
)  # fmt: skip

HOSPITAL_SUFFIXES: tuple[str, ...] = (
    "Hospital", "General Hospital", "Medical Centre", "Medical Center", "Medical Complex",
    "Clinic", "Family Clinic", "Diagnostic Centre", "Laboratories", "Teaching Hospital",
    "Children's Hospital", "Eye Hospital", "Health Centre", "Memorial Hospital",
    "Heart Institute", "Maternity Home", "Polyclinic", "Surgical Hospital",
)  # fmt: skip

# Well-known real institutions we must never emit verbatim (lower-cased substrings).
HOSPITAL_BLOCKLIST: tuple[str, ...] = (
    "shifa international", "aga khan", "shaukat khanum", "jinnah hospital", "mayo hospital",
    "services hospital", "liaquat national", "lahore general hospital", "indus hospital",
    "holy family", "civil hospital", "lady reading", "doctors hospital", "hameed latif",
    "south city", "ziauddin", "kulsum international", "maroof international",
)  # fmt: skip

EMAIL_DOMAINS: tuple[str, ...] = (
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "proton.me", "icloud.com",
    "live.com", "mail.com",
)  # fmt: skip

# --------------------------------------------------------------------------
# Non-PII clinical filler vocabulary (never annotated).
DIAGNOSES: tuple[str, ...] = (
    "type 2 diabetes mellitus", "essential hypertension", "community-acquired pneumonia",
    "acute gastroenteritis", "iron deficiency anaemia", "migraine without aura", "bronchial asthma",
    "urinary tract infection", "dengue fever", "typhoid fever", "hypothyroidism",
    "chronic kidney disease stage 3", "ischaemic heart disease", "osteoarthritis of the knee",
    "gastro-oesophageal reflux disease", "major depressive disorder", "cellulitis of the left leg",
    "acute appendicitis", "viral hepatitis B", "COPD exacerbation", "allergic rhinitis",
    "lower back pain", "pulmonary tuberculosis", "gestational diabetes", "atrial fibrillation",
)  # fmt: skip

COMPLAINTS: tuple[str, ...] = (
    "fever for three days", "shortness of breath", "chest pain on exertion", "persistent cough",
    "abdominal pain", "headache and dizziness", "burning micturition", "joint pain and swelling",
    "loose motions", "generalised weakness", "palpitations", "skin rash", "vomiting since morning",
    "lower back pain radiating to the leg", "blurred vision", "sore throat", "fatigue and weight loss",
    "swelling of both feet", "difficulty sleeping", "loss of appetite",
)  # fmt: skip

MEDICATIONS: tuple[str, ...] = (
    "Metformin 500 mg", "Amlodipine 5 mg", "Paracetamol 1 g", "Amoxicillin 500 mg",
    "Omeprazole 20 mg", "Atorvastatin 20 mg", "Salbutamol inhaler", "Levothyroxine 50 mcg",
    "Ceftriaxone 1 g IV", "Azithromycin 500 mg", "Insulin glargine 10 units", "Losartan 50 mg",
    "Aspirin 75 mg", "Ferrous sulphate 200 mg", "Cetirizine 10 mg", "Ibuprofen 400 mg",
    "Ondansetron 4 mg", "Pantoprazole 40 mg", "Bisoprolol 2.5 mg", "Sertraline 50 mg",
)  # fmt: skip

FREQUENCIES: tuple[str, ...] = (
    "once daily", "twice daily", "three times a day", "at bedtime", "every 8 hours", "as needed",
    "OD", "BD", "TDS", "PRN",
)  # fmt: skip

SPECIALTIES: tuple[str, ...] = (
    "Cardiology", "Internal Medicine", "Paediatrics", "Gynaecology", "Orthopaedics",
    "Pulmonology", "Nephrology", "Gastroenterology", "Endocrinology", "Neurology",
    "General Surgery", "Dermatology", "Psychiatry", "ENT", "Ophthalmology",
)  # fmt: skip

CREDENTIALS: tuple[str, ...] = (
    "MBBS", "MBBS, FCPS", "MBBS, MRCP", "FRCS", "MD", "MBBS, MCPS", "RN", "BSN",
)  # fmt: skip

WARDS: tuple[str, ...] = (
    "Medical Ward 2", "Surgical Ward B", "ICU", "CCU", "Paediatric Ward", "Emergency",
    "Female Medical Ward", "HDU", "OPD Room 14",
)  # fmt: skip

RELATIONS: tuple[tuple[str, str], ...] = (
    ("mother", "f"), ("father", "m"), ("husband", "m"), ("wife", "f"), ("son", "m"),
    ("daughter", "f"), ("brother", "m"), ("sister", "f"), ("guardian", "m"), ("uncle", "m"),
)  # fmt: skip

RELATIVE_DATES: tuple[str, ...] = (
    "yesterday", "two weeks ago", "last month", "three days ago", "this morning",
    "since last night", "a week ago", "earlier today",
)  # fmt: skip

DURATIONS: tuple[str, ...] = (
    "3 days", "one week", "two weeks", "10 days", "a month", "48 hours", "6 weeks",
)  # fmt: skip

# --------------------------------------------------------------------------
# Hard case: given names / surnames that are also ordinary English words.
AMBIG_FIRST_F: tuple[str, ...] = (
    "Hope",
    "Faith",
    "Grace",
    "Rose",
    "Joy",
    "Amber",
    "Iris",
    "Ruby",
    "June",
    "May",
    "Noor",
    "Dua",
    "Saba",
)
AMBIG_FIRST_M: tuple[str, ...] = (
    "Will",
    "Mark",
    "Frank",
    "Rich",
    "Hunter",
    "Bill",
    "Jack",
    "Guy",
    "Sunny",
    "Iqbal",
    "Victor",
)
AMBIG_LAST: tuple[str, ...] = (
    "Brown",
    "White",
    "Green",
    "Young",
    "King",
    "Black",
    "Hill",
    "Wood",
    "Bell",
    "Rose",
    "Hope",
    "May",
    "Iqbal",
)

# Entity-free clinical sentences. Several use name-words as ordinary words
# (Frank, Bell, Wood, White, Will, May, Hope, Rose, Young, Green, Black) —
# these are hard negatives for name detectors.
NARRATIVE: tuple[str, ...] = (
    "Frank blood was not seen on rectal examination.",
    "Bell's palsy was considered and excluded.",
    "Wood's lamp examination was negative.",
    "White cell count is within normal limits.",
    "Will review in clinic with the results.",
    "May require admission if symptoms worsen.",
    "The patient expressed hope of returning to work soon.",
    "Rose spots were not observed.",
    "Young adult with no known comorbidities.",
    "Green sputum was reported over the last few days.",
    "Black stools were denied.",
    "Chest is clear to auscultation bilaterally.",
    "Abdomen is soft and non-tender with no organomegaly.",
    "Heart sounds are normal with no added murmurs.",
    "There is no pedal oedema.",
    "Neurological examination is grossly intact.",
    "The surgical wound is clean and dry.",
    "Pain is controlled with oral analgesia.",
    "Oral intake has improved over the last 24 hours.",
    "Blood cultures are pending.",
    "Fluid balance was reviewed and found satisfactory.",
    "Dietary advice was given and understood.",
    "Smoking cessation was discussed.",
    "Red flag symptoms were explained in detail.",
    "Compliance with medication has been poor.",
    "There is mild tenderness in the right iliac fossa.",
    "Capillary refill time is less than 2 seconds.",
    "The patient is alert and oriented to time, place and person.",
    "Mobilising independently on the ward.",
    "Plan discussed with the team on the morning round.",
    "Repeat ECG shows normal sinus rhythm.",
    "Urine dipstick was negative for nitrites.",
    "Allergies: none known.",
    "Consent was obtained after explaining risks and benefits.",
    # More name-word negatives so every split gets several (review finding M2-6).
    "Grace period of one week was given before the repeat test.",
    "Iris examination was unremarkable.",
    "Amber-coloured urine was noted in the catheter bag.",
    "Joy and interest in daily activities are reduced.",
    "Hope for full recovery was discussed with the family.",
    "Mark the operative site before transfer to theatre.",
    "Bill for the procedure was forwarded to accounts.",
    "Hunter's canal block was performed for analgesia.",
    "King's College criteria were not met.",
    "Faith-based dietary preferences were respected.",
    "Brown discharge was reported on the dressing.",
    "Hill walking is not advised for six weeks.",
    "June review was moved to an earlier slot.",
)  # fmt: skip

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip

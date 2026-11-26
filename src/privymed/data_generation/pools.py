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

PK_BUILDING_WORDS: tuple[str, ...] = (
    "Al-Noor", "Rehmat", "Sitara", "Gulzar", "Hilal", "Falak", "Shadab", "Mehran", "Zarghoon",
    "Margalla", "Kohinoor", "Sapphire",
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
    "Zarghoon", "Margalla View", "Indus Valley", "Lakeside", "Noor-ul-Huda", "Fatimid Care",
    "Saint Brendan", "Westbrook", "Harbour", "Maple Grove", "Kohsar", "Mehran",
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

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip

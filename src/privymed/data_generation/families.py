"""Template families: 24 families across 9 clinical document types.

Each family is a structurally distinct way of writing a document type
(formal letter vs. terse shorthand vs. key-value form ...). Families are the
unit of the train/dev/test split, so test-set *structures* are never seen in
training. See ``engine.py`` for the template syntax.

Authoring rules (enforced by ``tests/test_families.py``):
* put spaces *inside* optional choices: ``{x}[[| (MRN {y})]]`` not ``{x} [[|(MRN {y})]]``;
* titles (Dr., Mr.) and credentials are literal text outside name slots;
* every family must produce at least three entity types.
"""

from __future__ import annotations

from dataclasses import replace

from privymed.data_generation.engine import Section as S
from privymed.data_generation.engine import TemplateFamily as F

# ============================================================================ discharge
DIS_FORMAL = F(
    "dis_formal",
    "discharge_summary",
    (
        S(("{hospital}\n[[Department of {specialty}|{specialty} Unit|{ward}]]",)),
        S(("DISCHARGE SUMMARY", "Discharge Summary", "DISCHARGE NOTE")),
        S(
            (
                "Patient Name: {patient.name}\nMRN: {patient.mrn}\nDate of Birth: {patient.dob}\nAge/Sex: {age}/{sex}",
                "Name: {patient.name:upper}    MR#: {patient.mrn}\nDOB: {patient.dob}    CNIC: {patient.cnic}",
            )
        ),
        S(
            (
                "Date of Admission: {date.admit}\nDate of Discharge: {date.discharge}",
                "Admitted: {date.admit}  Discharged: {date.discharge}",
            )
        ),
        S(("Diagnosis: {diagnosis}", "Final Diagnosis: {diagnosis}")),
        S(
            (
                "Hospital Course:\n{patient.title} {patient.name:last_only} is a {age}-year-old {sex} who presented with {complaint}. {patient.subj_cap} was managed with {medication} and improved.",
                "Hospital Course:\nPresented with {complaint}. Treatment included {medication} {freq}. Recovery was uneventful.",
            )
        ),
        S(("Discharge Medications:\n1. {medication} {freq}\n2. {medication2} {freq2}",)),
        S(("Follow-up: {specialty} OPD on {date.followup}[[| at {time}]].",), p=0.8),
        S(
            (
                "Attending Consultant: Dr. {staff1.name}, {staff1.credential}",
                "Signed: Dr. {staff1.name:initial_last}",
            )
        ),
    ),
)

DIS_LETTER = F(
    "dis_letter",
    "discharge_summary",
    (
        S(("{hospital}\n{hospital.address}\nTel: {hospital.phone}",)),
        S(("{date.discharge}",)),
        S(("Dear Dr. {staff2.name:last_only},", "Dear Colleague,")),
        S(
            (
                "I am writing to inform you that your patient, {patient.name} (DOB {patient.dob}, MRN {patient.mrn}), was admitted under my care on {date.admit} with {complaint} and was discharged on {date.discharge}.",
                "Your patient {patient.title} {patient.name} was admitted to {hospital} on {date.admit} and discharged home on {date.discharge}.",
            )
        ),
        S(
            (
                "The working diagnosis was {diagnosis}. During {patient.poss} stay {patient.subj} received {medication} and {medication2}.[[ {patient.poss_cap} {relative.relation}, {relative.name}, was present throughout the admission.|]]",
            )
        ),
        S(("Please review {patient.obj} in clinic in {duration}.",)),
        S(("Yours sincerely,\n\nDr. {staff1.name}\n{staff1.credential}\n{specialty}, {hospital}",)),
    ),
    sep="\n\n",
)

DIS_TERSE = F(
    "dis_terse",
    "discharge_summary",
    (
        S(("D/C SUMMARY - {hospital}", "DC SUMM / {hospital}")),
        S(("Pt: {patient.name:upper} | MRN {patient.mrn} | {age}{sex_short}",)),
        S(("DOA {date.admit} DOD {date.discharge}",)),
        S(("Dx: {diagnosis}",)),
        S(("c/o {complaint} x {duration}. Rx {medication} {freq}, {medication2} {freq2}.",)),
        S(("Vitals at d/c: BP {bp}, HR {pulse}, T {temp}F",), p=0.7),
        S(("F/U {date.followup} w/ Dr {staff1.name:last_only}[[| ({staff1.phone})]]",)),
        S(("NOK: {relative.name} ({relative.relation}) {relative.phone}",), p=0.6),
    ),
)

# ============================================================================ OPD notes
OPD_SOAP = F(
    "opd_soap",
    "opd_note",
    (
        S(("{hospital} - {specialty} OPD", "OPD Note | {hospital}")),
        S(("Date: {date.visit}   Time: {time}",)),
        S(("Patient: {patient.name}, {age}y {sex_short}, MRN {patient.mrn}",)),
        S(("S: {complaint} since {rel_date}.",)),
        S(("O: BP {bp}, pulse {pulse}/min, temp {temp}F, SpO2 {sats}%.",)),
        S(("A: {diagnosis}.",)),
        S(("P: {medication} {freq} for {duration}. Review on {date.followup}.",)),
        S(("Seen by: Dr. {staff1.name} ({specialty})",)),
    ),
)

OPD_PROSE = F(
    "opd_prose",
    "opd_note",
    (
        S(
            (
                "{patient.title} {patient.name} attended the {specialty} clinic at {hospital} on {date.visit} accompanied by {patient.poss} {relative.relation}, {relative.name}.",
                "{patient.name}, a {age}-year-old {sex} from {city}, was seen in clinic today ({date.visit}).",
            )
        ),
        S(
            (
                "{patient.subj_cap} reports {complaint} for {duration}.[[ No significant past history.| Known case of {diagnosis2}.|]]",
            )
        ),
        S(("On examination BP was {bp} mmHg and pulse {pulse} bpm.",)),
        S(("Impression: {diagnosis}. Started on {medication} {freq}.",)),
        S(("Contact number on file: {patient.phone}.",), p=0.5),
        S(("Dr. {staff1.name:initial_last}", "- {staff1.name}, {staff1.credential}")),
    ),
    sep=" ",
)

OPD_BULLETS = F(
    "opd_bullets",
    "opd_note",
    (
        S(("VISIT SUMMARY", "Clinic Visit Summary")),
        S(
            (
                "- Name: {patient.name:last_first}\n- DOB: {patient.dob}\n- CNIC: {patient.cnic}\n- Phone: {patient.phone}",
                "* Patient: {patient.name}\n* Date of birth: {patient.dob}\n* Contact: {patient.phone}",
            )
        ),
        S(("- Visit date: {date.visit}\n- Clinic: {hospital}\n- Clinician: Dr. {staff1.name}",)),
        S(
            (
                "- Presenting complaint: {complaint}\n- Assessment: {diagnosis}\n- Plan: {medication}, {freq}",
            )
        ),
        S(("- Next appointment: {date.followup}",), p=0.7),
    ),
)

# ============================================================================ referrals
REF_LETTER = F(
    "ref_letter",
    "referral",
    (
        S(("{hospital}\n{hospital.address}\nPhone: {hospital.phone} | Email: {hospital.email}",)),
        S(("Date: {date.visit}",)),
        S(("To: Dr. {staff2.name}, {specialty}, {hospital2}",)),
        S(("Re: {patient.name}, DOB {patient.dob}, MRN {patient.mrn}",)),
        S(
            (
                "Dear Dr. {staff2.name:last_only},\nThank you for seeing this {age}-year-old {sex} with {complaint}.[[ {patient.subj_cap} has a background of {diagnosis2}.|]]",
            )
        ),
        S(
            (
                "I would be grateful for your opinion regarding {diagnosis}. Current medication: {medication} {freq}.",
            )
        ),
        S(("The patient can be contacted on {patient.phone}[[| or {patient.email}]].",)),
        S(("Kind regards,\nDr. {staff1.name}\n{staff1.credential}",)),
    ),
)

REF_FORM = F(
    "ref_form",
    "referral",
    (
        S(("REFERRAL FORM", "PATIENT REFERRAL SLIP")),
        S(
            (
                "Referring facility: {hospital}\nReferring doctor: Dr. {staff1.name}   Contact: {staff1.phone}",
            )
        ),
        S(("Referred to: {hospital2} ({specialty})",)),
        S(
            (
                "Patient name: {patient.name:upper}\nGuardian/NOK: {relative.name:upper} ({relative.relation})\nCNIC: {patient.cnic}\nAddress: {patient.address}",
            )
        ),
        S(("Reason for referral: {diagnosis}\nUrgency: [[Routine|Urgent|Emergency]]",)),
        S(("Date: {date.visit}",)),
    ),
)

REF_EMAIL = F(
    "ref_email",
    "referral",
    (
        S(
            (
                "From: {staff1.email}\nTo: {staff2.email}\nSubject: Referral - {patient.name:initial_last} ({patient.mrn})",
            )
        ),
        S(("Hi {staff2.name:first_only},", "Dear Dr. {staff2.name:last_only},")),
        S(
            (
                "Could you please see {patient.name} ({age}{sex_short}) at {hospital2} sometime after {date.followup}? [[{patient.subj_cap} was seen here on {date.visit} with {complaint}.|Seen on {date.visit} for {complaint}.]]",
            )
        ),
        S(("Working diagnosis is {diagnosis}. Patient phone: {patient.phone}.",)),
        S(("Thanks,\n{staff1.name:first_only}\n{hospital}",)),
    ),
    sep="\n\n",
)

# ============================================================================ prescriptions
RX_SLIP = F(
    "rx_slip",
    "prescription",
    (
        S(("{hospital}\n{hospital.address} | {hospital.phone}",)),
        S(("Dr. {staff1.name}\n{staff1.credential} | {specialty}",)),
        S(("Patient: {patient.name}    Age: {age}    Date: {date.visit}",)),
        S(
            (
                "Rx\n1. {medication} - {freq} x {duration}\n2. {medication2} - {freq2}[[|\n3. {medication3} - {freq3}]]",
            )
        ),
        S(("Next visit: {date.followup}",), p=0.6),
    ),
)

RX_LABEL = F(
    "rx_label",
    "prescription",
    (
        S(("{hospital} PHARMACY", "PHARMACY - {hospital}")),
        S(
            (
                "{patient.name:upper}  MRN:{patient.mrn}",
                "Pt: {patient.name:last_first} ({patient.mrn})",
            )
        ),
        S(("{medication}\nTake {freq} for {duration}",)),
        S(("Prescriber: Dr. {staff1.name:initial_last}  Dispensed: {date.visit}",)),
        S(("Rx No. {id.rx}",)),
    ),
)

RX_REFILL = F(
    "rx_refill",
    "prescription",
    (
        S(
            (
                "Refill request received on {date.visit} from {patient.name} ({patient.phone}) for {medication}.",
            )
        ),
        S(
            (
                "Last prescribed by Dr. {staff1.name} on {date.prev}. [[Approved for {duration}.|Patient asked to book a review first.]]",
            )
        ),
        S(("Patient ID {patient.mrn}; CNIC on file {patient.cnic}.",), p=0.6),
        S(("Processed by {staff2.name}, pharmacy desk.",)),
    ),
    sep=" ",
)

# ============================================================================ lab reports
LAB_TABLE = F(
    "lab_table",
    "lab_report",
    (
        S(("{hospital} - CLINICAL LABORATORY", "{hospital}\nDepartment of Pathology")),
        S(("Lab No: {id.lab}    Collected: {date.visit} {time}    Reported: {date.report}",)),
        S(
            (
                "Patient: {patient.name}   Age/Sex: {age}/{sex_short}   MRN: {patient.mrn}\nReferred by: Dr. {staff1.name}",
            )
        ),
        S(
            (
                "TEST              RESULT    UNITS     REF RANGE\n"
                "Haemoglobin       {hb}      g/dL      12.0-16.0\n"
                "WBC count         {wbc}     x10^9/L   4.0-11.0\n"
                "Platelets         {plt}     x10^9/L   150-400\n"
                "Fasting glucose   {glucose}       mg/dL     70-100",
            )
        ),
        S(("Verified by: {staff2.name}, [[Consultant Pathologist|Lab Technologist]]",)),
    ),
)

LAB_NARRATIVE = F(
    "lab_narrative",
    "lab_report",
    (
        S(
            (
                "Results for {patient.name:last_first} (MRN {patient.mrn}, DOB {patient.dob}) collected on {date.visit} are as follows: haemoglobin {hb} g/dL, creatinine {creatinine} mg/dL, fasting glucose {glucose} mg/dL.",
            )
        ),
        S(
            (
                "Results were discussed with Dr. {staff1.name} by phone at {time}.",
                "Dr. {staff1.name} has been informed.",
            )
        ),
        S(("Specimen ID {id.specimen}.",), p=0.7),
        S(("Report generated {date.report} - {hospital}.",)),
    ),
    sep=" ",
)

LAB_SMS = F(
    "lab_sms",
    "lab_report",
    (
        S(("{hospital}:", "Dear {patient.name:first_only},")),
        S(("your [[lab|test]] report ({id.lab}) [[is ready|is now available]].",)),
        S(("Collect from reception or call {hospital.phone}.",)),
        S(("Ref: Dr. {staff1.name:last_only}.",), p=0.5),
    ),
    sep=" ",
)

# ============================================================================ appointments
APPT_SMS = F(
    "appt_sms",
    "appointment",
    (
        S(("Reminder:", "{hospital}:")),
        S(
            (
                "{patient.title} {patient.name:last_only}, your appointment with Dr. {staff1.name:last_only} is on {date.followup} at {time}.",
                "Appt for {patient.name} on {date.followup}, {time}, with Dr. {staff1.name}.",
            )
        ),
        S(("Reply Y to confirm or call {hospital.phone}.",)),
    ),
    sep=" ",
)

APPT_EMAIL = F(
    "appt_email",
    "appointment",
    (
        S(("Subject: Appointment confirmation - {specialty}",)),
        S(("Dear {patient.title} {patient.name:last_only},",)),
        S(
            (
                "This is to confirm your appointment at {hospital} on {date.followup} at {time} with Dr. {staff1.name} ({specialty}).",
            )
        ),
        S(
            (
                "Your patient ID is {patient.mrn}. Please bring your CNIC ({patient.cnic}) and previous reports.",
                "Your patient ID is {patient.mrn}. Please bring your original CNIC and previous reports.",
            )
        ),
        S(("If you need to reschedule, email {hospital.email} or call {hospital.phone}.",)),
        S(("Regards,\n{staff3.name}\nPatient Services, {hospital}",)),
    ),
    sep="\n\n",
)

APPT_LIST = F(
    "appt_list",
    "appointment",
    (
        S(("{hospital} - {specialty} clinic list for {date.visit}",)),
        S(("Consultant: Dr. {staff1.name}",)),
        S(
            (
                "{time}  {patient.name:last_first}  MRN {patient.mrn}\n"
                "{time2}  {patient2.name:last_first}  MRN {patient2.mrn}\n"
                "{time3}  {patient3.name:last_first}  MRN {patient3.mrn}",
            )
        ),
        S(("Note: {patient2.name:first_only} needs an interpreter.",), p=0.4),
    ),
)

# ============================================================================ admission
ADM_FORM = F(
    "adm_form",
    "admission_form",
    (
        S(("{hospital}\nPATIENT ADMISSION FORM",)),
        S(("Admission No: {id.admission}    Date: {date.admit}    Ward: {ward}",)),
        S(
            (
                "Full Name: {patient.name}\nCNIC: {patient.cnic}\nDate of Birth: {patient.dob}\nGender: {sex}\nAddress: {patient.address}\nMobile: {patient.phone}\nEmail: {patient.email}",
            )
        ),
        S(
            (
                "Next of Kin: {relative.name}\nRelationship: {relative.relation}\nNOK Contact: {relative.phone}",
            )
        ),
        S(("Admitting Doctor: Dr. {staff1.name}",)),
        S(("Signature of patient/guardian: ________",)),
    ),
)

ADM_KV = F(
    "adm_kv",
    "admission_form",
    (
        S(("REG | {hospital} | {date.admit} {time}",)),
        S(
            (
                "NAME={patient.name:upper};DOB={patient.dob:iso};CNIC={patient.cnic};MRN={patient.mrn}",
                "name: {patient.name:lower} / dob: {patient.dob} / mrn: {patient.mrn}",
                # CSV export: entities separated only by commas (adjacency hard case).
                "{patient.name},{patient.cnic},{patient.dob:iso},{patient.phone},{patient.mrn}",
            )
        ),
        S(("ADDR={patient.address}",)),
        S(("PH={patient.phone};NOK={relative.name} ({relative.relation}) {relative.phone}",)),
        S(("REGISTERED_BY={staff3.name:initial_last}",)),
    ),
)

# ============================================================================ progress notes
PROG_WARD = F(
    "prog_ward",
    "progress_note",
    (
        S(("Ward round - {ward}, {date.visit}",)),
        S(
            (
                "{patient.name:last_only}, bed [[4|7|12|15]]: {patient.subj} is [[feeling better|still febrile|comfortable]] today. BP {bp}, HR {pulse}.",
            )
        ),
        S(
            (
                "Plan: continue {medication}; [[repeat bloods tomorrow|chest X-ray today|discharge if stable]].",
            )
        ),
        S(
            (
                "Discussed with {patient.poss} {relative.relation} {relative.name:first_only} at bedside.",
            ),
            p=0.5,
        ),
        S(("Dr. {staff2.name:initial_last} (on behalf of Dr. {staff1.name})",)),
    ),
)

PROG_NURSING = F(
    "prog_nursing",
    "progress_note",
    (
        S(("NURSING NOTE {date.visit} {time}",)),
        S(
            (
                "Pt {patient.name} (MRN {patient.mrn}) [[resting comfortably|complained of pain|ambulating with assistance]]. Vitals: T {temp}, P {pulse}, BP {bp}, SpO2 {sats}%.",
            )
        ),
        S(("{medication} given as charted.",)),
        S(("Family ({relative.relation}) called on {relative.phone}, updated.",), p=0.5),
        S(("- {staff3.name}, RN",)),
    ),
)

# ============================================================================ radiology
RAD_REPORT = F(
    "rad_report",
    "radiology_report",
    (
        S(("{hospital}\nDEPARTMENT OF RADIOLOGY",)),
        S(
            (
                "Patient: {patient.name}   MRN: {patient.mrn}   DOB: {patient.dob}\n"
                "Exam: [[Chest X-ray PA view|Ultrasound abdomen|CT brain without contrast|MRI lumbar spine]]   Accession: {id.accession}\n"
                "Date of exam: {date.visit}\nReferring physician: Dr. {staff1.name}",
            )
        ),
        S(
            (
                "FINDINGS:\n[[No acute abnormality is seen.|There is mild degenerative change.|Findings are in keeping with {diagnosis}.]]",
            )
        ),
        S(
            (
                "IMPRESSION:\n[[Normal study.|Clinical correlation is advised.|Follow-up imaging in {duration} is recommended.]]",
            )
        ),
        S(("Reported by: Dr. {staff2.name}, Consultant Radiologist, on {date.report}",)),
    ),
)

RAD_BRIEF = F(
    "rad_brief",
    "radiology_report",
    (
        S(("{patient.name:upper} {patient.mrn} {date.visit}",)),
        S(
            (
                "US ABD: [[normal liver and gall bladder|fatty liver grade I|small renal calculus on the left]].",
                "CXR: [[clear lung fields|right lower zone consolidation|cardiomegaly]].",
            )
        ),
        S(("Dict. Dr {staff2.name:last_only} / typed {staff3.name:initial_last} {date.report}",)),
    ),
)

# ============================================================================ contact-heavy (balance)
ADM_INSURANCE = F(
    "adm_insurance",
    "admission_form",
    (
        S(("{hospital} - PANEL / INSURANCE ADMISSION", "INSURANCE PRE-AUTHORISATION | {hospital}")),
        S(("Claim ref: {id.claim}    Date: {date.admit}",)),
        S(
            (
                "Policy holder: {relative.name} ({relative.relation})\nHolder CNIC: {relative.cnic}\nHolder email: {relative.email}",
                "Insured member: {relative.name:last_first}, CNIC {relative.cnic}, contact {relative.phone}",
            )
        ),
        S(
            (
                "Patient: {patient.name}\nPatient CNIC: {patient.cnic}\nDOB: {patient.dob}\nResidential address: {patient.address}\nMobile: {patient.phone}",
            )
        ),
        S(("Correspondence address: {relative.address}",), p=0.5),
        S(("Provisional diagnosis: {diagnosis}\nTreating doctor: Dr. {staff1.name}",)),
        S(("Verified by {staff3.name}, Admissions Office",)),
    ),
)

APPT_BOOKING = F(
    "appt_booking",
    "appointment",
    (
        S(("Online Booking Confirmation", "Your appointment is booked")),
        S(("Booking reference: {id.booking}",)),
        S(
            (
                "Name: {patient.name}\nEmail: {patient.email}\nMobile: {patient.phone}\nCNIC: {patient.cnic}",
                "Booked for {patient.title} {patient.name} (CNIC {patient.cnic}). Contact: {patient.email}, {patient.phone}.",
            )
        ),
        S(("Clinic: {hospital}, {hospital.address}",)),
        S(("Doctor: Dr. {staff1.name} ({specialty})\nDate: {date.followup}   Time: {time}",)),
        S(("A confirmation has been sent to {patient.email}.",), p=0.6),
        S(("Questions? Write to {hospital.email} or call {hospital.phone}.",)),
    ),
)

# ============================================================================ entity-free (hard negatives)
EDU_LEAFLET = F(
    "edu_leaflet",
    "non_phi",
    (
        S(("PATIENT INFORMATION: [[Managing|Living with|About]] {diagnosis}",)),
        S(("{narrative}",)),
        S(("Take your medicines exactly as prescribed, for example {medication} {freq}.",)),
        S(
            (
                "If symptoms persist for more than {duration}, contact your doctor or visit the nearest emergency department.",
            )
        ),
        S(
            (
                "Clinic hours: 8:00 AM - 2:00 PM, Monday to Saturday. Ward 4 visiting time is after {time}.",
            )
        ),
        S(("{narrative2}",), p=0.7),
    ),
    sep="\n\n",
    tags=("entity_free",),
)

PROTOCOL_NOTE = F(
    "protocol_note",
    "non_phi",
    (
        S(
            (
                "[[{specialty}|Ward]] Protocol: [[Sepsis screening|Insulin sliding scale|Fall prevention|Pre-operative checklist]]",
            )
        ),
        S(("Version [[2.1|3.0|1.4]] - reviewed [[annually|every two years]].",)),
        S(
            (
                "1. Check vital signs every [[4|6|8]] hours; escalate if BP is below 90/60 or saturation below 92%.\n"
                "2. {narrative}\n"
                "3. Document all doses of {medication} in the drug chart.\n"
                "4. Inform the on-call doctor if there is no improvement within {duration}.",
            )
        ),
        S(
            (
                "Reference ranges: haemoglobin 12.0-16.0 g/dL, WBC 4.0-11.0 x10^9/L, platelets 150-400.",
            )
        ),
    ),
    tags=("entity_free",),
)

ADMIN_MEMO = F(
    "admin_memo",
    "non_phi",
    (
        S(("STAFF NOTICE", "Internal Memo - {specialty} Department", "CIRCULAR No. [[12|27|41]]")),
        S(
            (
                "All doctors and nursing staff are informed that the {ward} will be closed for maintenance [[next week|from Monday|this weekend]].",
                "OPD timings will change to 9:00 AM - 1:00 PM during the holidays.",
            )
        ),
        S(("Patients due for review should be rebooked within {duration}. {narrative}",)),
        S(
            (
                "Extension 214 is the new number for the duty office; dial 0 for the operator.",
                "Room 14 and Room 15 will be used for triage until further notice.",
            ),
            p=0.7,
        ),
        S(("- Medical Superintendent's Office", "- Nursing Administration")),
    ),
    tags=("entity_free",),
)

# Where an entity-free narrative paragraph may follow a section (prose-like families only).
_NARRATIVE_AFTER: dict[str, tuple[int, ...]] = {
    "dis_formal": (5,),
    "dis_letter": (3, 4),
    "opd_soap": (4,),
    "opd_prose": (2,),
    "ref_letter": (4,),
    "ref_email": (2,),
    "rx_refill": (1,),
    "lab_narrative": (1,),
    "prog_ward": (1,),
    "prog_nursing": (1,),
    "rad_report": (2,),
}

_BASE: tuple[F, ...] = (
    DIS_FORMAL, DIS_LETTER, DIS_TERSE,
    OPD_SOAP, OPD_PROSE, OPD_BULLETS,
    REF_LETTER, REF_FORM, REF_EMAIL,
    RX_SLIP, RX_LABEL, RX_REFILL,
    LAB_TABLE, LAB_NARRATIVE, LAB_SMS,
    APPT_SMS, APPT_EMAIL, APPT_LIST, APPT_BOOKING,
    ADM_FORM, ADM_KV, ADM_INSURANCE,
    PROG_WARD, PROG_NURSING,
    RAD_REPORT, RAD_BRIEF,
    EDU_LEAFLET, PROTOCOL_NOTE, ADMIN_MEMO,
)  # fmt: skip

FAMILIES: tuple[F, ...] = tuple(
    replace(f, narrative_after=_NARRATIVE_AFTER.get(f.family_id, ())) for f in _BASE
)

FAMILIES_BY_ID: dict[str, F] = {f.family_id: f for f in FAMILIES}

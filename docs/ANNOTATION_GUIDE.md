# Annotation guide

These rules define what counts as an entity and where its boundaries are. The generator, the manually verified OOD set, and every detector's output mapping must follow them. Where a rule is a judgement call, the reason is given so it can be defended.

## General

- Spans are half-open character intervals `[start, end)` over the original text (Unicode code points).
- Spans never start or end with whitespace or invisible characters, and gold spans never overlap.
- When something is ambiguous, ask: *would leaving this unredacted help someone identify the person?*

## Per type

| Type | Include | Exclude | Notes |
|---|---|---|---|
| PATIENT | Given names, surnames, initials+surname, full names of patients **and their relatives** (e.g. "mother, Saima Khan") | Titles (`Mr.`, `Mrs.`, `Ms.`), honorifics, possessive `'s` | Relatives are PATIENT because they identify the patient. |
| STAFF | Names of doctors, nurses, technicians, other staff | Titles (`Dr.`, `Prof.`), credentials (`MBBS`, `FCPS`, `MD`), roles ("consultant") | `Dr. [STAFF], FCPS` keeps context useful for detection. Follows i2b2 practice of excluding titles. |
| DATE | Full and partial calendar dates: `12/03/2024`, `March 2024`, `12 March`, dates of birth | Times of day (`10:30 AM`), relative expressions (`yesterday`, `2 weeks ago`), durations, bare years used as ages, **bare month names** (`in June`; `May` as a word) | In `12/03/2024 10:30`, only the date is annotated. Relative dates do not identify on their own. |
| PHONE | Phone and fax numbers incl. country code, parentheses, separators | Extension words (`ext.`) | |
| EMAIL | The whole address | Surrounding `mailto:` or angle brackets | |
| CNIC | 13-digit Pakistani national ID in any separator style | The label "CNIC:" | |
| ID | MRNs, patient IDs, admission/lab/accession numbers, including prefixes **internal to the identifier** (`MRN-2024-000123`, `#1913619`, `LAB24-00112`) | **Field labels** ending in `:` or `=` (`MRN:`, `MRN=`, `Patient ID:`), **even when glued** to the value (`MRN:7159-0324-03` → span is `7159-0324-03`) | Rule: a prefix joined by `-` or `#` is part of the ID; a prefix joined by `:` or `=` is a field label. Same rule for CNIC (`CNIC=…`). |
| ADDRESS | Street, house/flat/plot, locality, city, postcode, country **when part of an address** | A city mentioned alone as context ("referred from Lahore") | Single-city mentions are not annotated, which keeps the label definition consistent. |
| HOSPITAL | Names and acronyms of hospitals, clinics, labs | Generic references ("the hospital", "OPD", "ward 4") | A city following the name in parentheses is not part of the span. |

## Noise and typos

Typos and case changes are part of the text: if a name is written `Ayseha Siddiqui`, the gold span covers the misspelled string. Gold spans created through noise carry `fmt` suffix `+typo`.

## Not annotated (deliberately)

Ages, professions, diagnoses, medications, generic places, and times. These are out of scope for the 9-type schema (ADR-002). Ages above 89 are a known HIPAA identifier; excluding them is a documented limitation.

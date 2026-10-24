"""Explicit mapping configuration and transformation dictionaries for Topia to Equus."""

import re
from datetime import date, datetime
from typing import Any

# Standard ISO-3166-1 alpha-3 country lookup
ISO3_COUNTRY_MAP: dict[str, str] = {
    # Common Topia / Equus Country Names & 2-letter codes
    "AFGHANISTAN": "AFG",
    "ALBANIA": "ALB",
    "ALGERIA": "DZA",
    "AMERICAN SAMOA": "ASM",
    "ANDORRA": "AND",
    "ANGOLA": "AGO",
    "ARGENTINA": "ARG",
    "ARMENIA": "ARM",
    "AUSTRALIA": "AUS",
    "AUSTRIA": "AUT",
    "AZERBAIJAN": "AZE",
    "BAHAMAS": "BHS",
    "BAHRAIN": "BHR",
    "BANGLADESH": "BGD",
    "BELGIUM": "BEL",
    "BRAZIL": "BRA",
    "CANADA": "CAN",
    "CHILE": "CHL",
    "CHINA": "CHN",
    "COLOMBIA": "COL",
    "COSTA RICA": "CRI",
    "CROATIA": "HRV",
    "CZECH REPUBLIC": "CZE",
    "DENMARK": "DNK",
    "EGYPT": "EGY",
    "FINLAND": "FIN",
    "FRANCE": "FRA",
    "GERMANY": "DEU",
    "GREECE": "GRC",
    "HONG KONG": "HKG",
    "HUNGARY": "HUN",
    "INDIA": "IND",
    "INDONESIA": "IDN",
    "IRELAND": "IRL",
    "ISRAEL": "ISR",
    "ITALY": "ITA",
    "JAPAN": "JPN",
    "JORDAN": "JOR",
    "KENYA": "KEN",
    "KOREA, REPUBLIC OF": "KOR",
    "SOUTH KOREA": "KOR",
    "KUWAIT": "KWT",
    "LEBANON": "LBN",
    "LUXEMBOURG": "LUX",
    "MALAYSIA": "MYS",
    "MEXICO": "MEX",
    "MOROCCO": "MAR",
    "NETHERLANDS": "NLD",
    "NEW ZEALAND": "NZL",
    "NORWAY": "NOR",
    "OMAN": "OMN",
    "PAKISTAN": "PAK",
    "PHILIPPINES": "PHL",
    "POLAND": "POL",
    "PORTUGAL": "PRT",
    "QATAR": "QAT",
    "ROMANIA": "ROU",
    "RUSSIA": "RUS",
    "RUSSIAN FEDERATION": "RUS",
    "SAUDI ARABIA": "SAU",
    "SINGAPORE": "SGP",
    "SOUTH AFRICA": "ZAF",
    "SPAIN": "ESP",
    "SWEDEN": "SWE",
    "SWITZERLAND": "CHE",
    "TAIWAN": "TWN",
    "THAILAND": "THA",
    "TURKEY": "TUR",
    "UNITED ARAB EMIRATES": "ARE",
    "UAE": "ARE",
    "UNITED KINGDOM": "GBR",
    "UK": "GBR",
    "GREAT BRITAIN": "GBR",
    "UNITED STATES": "USA",
    "UNITED STATES OF AMERICA": "USA",
    "US": "USA",
    "VIETNAM": "VNM",
}

# 2-letter code lookup
ISO2_TO_ISO3: dict[str, str] = {
    "AF": "AFG",
    "AL": "ALB",
    "DZ": "DZA",
    "AR": "ARG",
    "AU": "AUS",
    "AT": "AUT",
    "BE": "BEL",
    "BR": "BRA",
    "CA": "CAN",
    "CL": "CHL",
    "CN": "CHN",
    "CO": "COL",
    "CR": "CRI",
    "CZ": "CZE",
    "DK": "DNK",
    "EG": "EGY",
    "FI": "FIN",
    "FR": "FRA",
    "DE": "DEU",
    "GR": "GRC",
    "HK": "HKG",
    "HU": "HUN",
    "IN": "IND",
    "ID": "IDN",
    "IE": "IRL",
    "IL": "ISR",
    "IT": "ITA",
    "JP": "JPN",
    "KR": "KOR",
    "KW": "KWT",
    "LU": "LUX",
    "MY": "MYS",
    "MX": "MEX",
    "NL": "NLD",
    "NZ": "NZL",
    "NO": "NOR",
    "OM": "OMN",
    "PH": "PHL",
    "PL": "POL",
    "PT": "PRT",
    "QA": "QAT",
    "RO": "ROU",
    "RU": "RUS",
    "SA": "SAU",
    "SG": "SGP",
    "ZA": "ZAF",
    "ES": "ESP",
    "SE": "SWE",
    "CH": "CHE",
    "TW": "TWN",
    "TH": "THA",
    "TR": "TUR",
    "AE": "ARE",
    "GB": "GBR",
    "US": "USA",
    "VN": "VNM",
}

# Values that must be converted to empty/blank
NOT_PROVIDED_VALUES: set[str] = {
    "not provided",
    "not-provided",
    "not_provided",
    "n/a",
    "na",
    "none",
    "-",
    "",
    "null",
    "undefined",
}

# Dropdown translations per field or general category
DROPDOWN_MAPS: dict[str, dict[str, str]] = {
    "GENDER": {
        "male": "Male",
        "m": "Male",
        "female": "Female",
        "f": "Female",
        "non-binary": "Other",
        "other": "Other",
    },
    "EMPLOYMENT_STATUS": {
        "employed": "Active",
        "active": "Active",
        "terminated": "Inactive",
        "inactive": "Inactive",
        "on leave": "On Leave",
        "resigned": "Inactive",
    },
    "PERSON_STATUS": {
        "employee": "Employee",
        "contractor": "Contractor",
        "intern": "Intern",
        "expatriate": "Expatriate",
    },
    "MARITAL_STATUS": {
        "married": "Married",
        "single": "Single",
        "divorced": "Divorced",
        "widowed": "Widowed",
        "separated": "Separated",
        "domestic partner": "Partner",
        "partner": "Partner",
    },
    "YES_NO": {
        "yes": "Yes",
        "y": "Yes",
        "true": "Yes",
        "1": "Yes",
        "no": "No",
        "n": "No",
        "false": "No",
        "0": "No",
    },
    "SPOUSE_RELATIONSHIP": {
        "spouse": "Spouse",
        "partner": "Partner",
        "domestic partner": "Partner",
        "wife": "Spouse",
        "husband": "Spouse",
    },
    "SPOUSE_STATUS": {
        "on assignment": "On Assignment",
        "at host": "On Assignment",
        "not at host": "Not at Host",
        "home": "Not at Host",
    },
}

# Explicit Assignment Identifier Strategy Options:
# STRATEGY_TOPIA_ID_WITH_FALLBACK (Default Reference): Topia Assignment ID is primary;
# falls back to Employee Number if missing/null.
# STRATEGY_EMPLOYEE_NUMBER (Client Test File): Column 5 receives Employee Number directly;
# Topia ID is stored in CF_TEXT029.
# NOTE: Final decision between these strategies requires client business confirmation.
STRATEGY_TOPIA_ID_WITH_FALLBACK = "TOPIA_ID_WITH_FALLBACK"
STRATEGY_EMPLOYEE_NUMBER = "EMPLOYEE_NUMBER"
DEFAULT_ASSIGNMENT_IDENTIFIER_STRATEGY = STRATEGY_EMPLOYEE_NUMBER

# Source row-2 technical fields whose spelling differs from the Equus headers.
# (regex_pattern, replacement_string) applied in order to upper-cased technical keys.
KEY_ALIASES: list[tuple[str, str]] = [
    (r"^(ASSIGNMENT!(?:FROM|TO)_COMPANY)_LEVEL(\d)$", r"\1_SEGMENT_LEVEL_\2"),
    (r"^ASSIGNMENT!GROUP$", "ASSIGNMENT!GROUP_NAME"),
    (r"^EMPLOYEE!SYSTEM_NUMBER$", "Employee Number"),
]

# Source columns whose row 2 is a note, a wrong field, or a missing field.
# Keyed by normalized (lower-case, single-spaced) Topia row-4 label.
# Value None = deliberately not migrated / drives derived business rule.
FIELD_OVERRIDES: dict[str, str | None] = {
    "assignment id": "ASSIGNMENT_CF!CF_TEXT029",  # Topia File Number (legacy id)
    "nationality 3": "EMPLOYEE_CF!CF_TEXT013",
    "status category": "ASSIGNMENT!PHASE",
    "home cost center name": "ASSIGNMENT_CF!CF_TEXT023",
    "host cost center name": "ASSIGNMENT_CF!CF_TEXT024",
    "host job level": "ASSIGNMENT!TO_SALARY_GRADE",  # Topia row 2 typo had TO_TITLE
    "home job level": "ASSIGNMENT!FROM_SALARY_GRADE",
    "home position id": "ASSIGNMENT_CF!CF_TEXT005",
    "host position id": "ASSIGNMENT_CF!CF_TEXT009",
    "cancellation reason": None,  # Drives derived rule ASSIGNMENT!PHASE = 'Cancelled'
}

# Verified address columns in source mapped to Equus LOCATION_TYPE
ADDRESS_COLUMNS: dict[str, str] = {
    "personal home address with effective date": "Departure Residence",
    "work home address with effective date": "Departure Office",
    "personal host address with effective date": "Destination Residence",
    "work host address with effective date": "Destination Office",
    "personal home address": "Departure Residence",
    "work home address": "Departure Office",
    "personal host address": "Destination Residence",
    "work host address": "Destination Office",
    "host residence address": "Destination Residence",
    "host address": "Destination Residence",
    "home address": "Departure Residence",
    "departure residence": "Departure Residence",
    "destination residence": "Destination Residence",
    "departure office": "Departure Office",
    "destination office": "Destination Office",
}

# Verified contact columns in source mapped to (LOCATION_TYPE, CONTACT_TYPE)
CONTACT_COLUMNS: dict[str, tuple[str, str]] = {
    "mobile phone number": ("Personal Mobile", "Telephone"),
    "phone number": ("Personal Mobile", "Telephone"),
    "personal email": ("Employee Preferred", "Email"),
    "email": ("Employee Preferred", "Email"),
    "work phone": ("Work", "Telephone"),
    "emergency phone": ("Emergency", "Telephone"),
}

# Verified dependent columns in source mapped to Equus DEPENDENT fields
DEPENDENT_FIELD_MAP: dict[str, str] = {
    "dependent first name": "ASSIGNMENT_DEPENDENT!FIRST_NAME",
    "dependent last name": "ASSIGNMENT_DEPENDENT!LAST_NAME",
    "dependent middle name": "ASSIGNMENT_DEPENDENT!MIDDLE_NAME",
    "dependent relationship": "ASSIGNMENT_DEPENDENT!RELATIONSHIP",
    "dependent gender": "ASSIGNMENT_DEPENDENT!GENDER",
    "dependent date of birth": "ASSIGNMENT_DEPENDENT!BIRTH_DATE",
    "dependent birth date": "ASSIGNMENT_DEPENDENT!BIRTH_DATE",
    "dependent dob": "ASSIGNMENT_DEPENDENT!BIRTH_DATE",
    "dependent at host": "ASSIGNMENT_DEPENDENT!STATUS",
    "dependent status": "ASSIGNMENT_DEPENDENT!STATUS",
    "spouse first name": "ASSIGNMENT_DEPENDENT!FIRST_NAME",
    "spouse last name": "ASSIGNMENT_DEPENDENT!LAST_NAME",
    "spouse middle name": "ASSIGNMENT_DEPENDENT!MIDDLE_NAME",
    "spouse relationship": "ASSIGNMENT_DEPENDENT!RELATIONSHIP",
    "spouse gender": "ASSIGNMENT_DEPENDENT!GENDER",
    "spouse date of birth": "ASSIGNMENT_DEPENDENT!BIRTH_DATE",
    "spouse birth date": "ASSIGNMENT_DEPENDENT!BIRTH_DATE",
    "spouse dob": "ASSIGNMENT_DEPENDENT!BIRTH_DATE",
    "spouse status": "ASSIGNMENT_DEPENDENT!STATUS",
}

# UNRESOLVED CLIENT-DEPENDENT RULES (Documented for client confirmation):
# 1. RESOURCE_MAP: Empty awaiting client-provided list of Topia names/emails -> Equus usernames.
RESOURCE_MAP: dict[str, str] = {}
# 2. DEPENDENT_IMPORT: 'Dependent Import' worksheet contains no employee key.
# Cannot join without client specification.
# 3. ADDRESS_COMPONENTS: Client must clarify if City/Postal/Country need regex extraction.
# 4. PII_NATIONALITY: Third nationality exclusion policy awaiting confirmation.


def normalize_identifier(val: Any) -> str | None:
    """Normalize identifier safely, converting IEEE-754 floats (e.g. 60936.0) to strings."""
    clean = clean_not_provided(val)
    if clean is None:
        return None
    if isinstance(clean, float):
        if clean.is_integer():
            return str(int(clean))
        return str(clean)
    s = str(clean).strip()
    if re.match(r"^\d+\.0$", s):
        return s[:-2]
    return s


def split_multiline_address(val: Any) -> tuple[str | None, str | None, str | None]:
    """Split multiline address string by newline into (line_1, line_2, line_3)."""
    clean = clean_not_provided(val)
    if not clean:
        return None, None, None
    lines = [line.strip() for line in str(clean).splitlines() if line.strip()]
    line_1 = lines[0] if len(lines) > 0 else None
    line_2 = lines[1] if len(lines) > 1 else None
    line_3 = ", ".join(lines[2:]) if len(lines) > 2 else None
    return line_1, line_2, line_3


# Explicit exception mapping: Topia source fields -> Equus technical fields
# Handles fields where technical header in Topia does not match Equus directly
EXPLICIT_SOURCE_FIELD_EXCEPTIONS: dict[str, str] = {
    "ASSIGNMENT ID": "ASSIGNMENT!ASSIGNMENT_IDENTIFIER",
    "EMPLOYEE ID": "EMPLOYEE!EMPLOYEE_NUMBER",
    "TALENT LINK ID": "EMPLOYEE!EMPLOYEE_NUMBER",
    "BUSINESS TITLE": "ASSIGNMENT_CF!CF_TEXT014",
    "PERSON STATUS": "EMPLOYEE!TYPE",
    "DATE OF BIRTH": "EMPLOYEE!BIRTH_DATE",
}


def clean_not_provided(val: Any) -> Any:
    """Convert 'Not Provided', 'N/A', etc. to None."""
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in NOT_PROVIDED_VALUES:
        return None
    return val


def convert_country_to_iso3(val: Any) -> tuple[str | None, str | None]:
    """Convert country name or 2-letter code to ISO-3 alpha-3 code.

    Returns: (iso3_code, warning_code)
    """
    clean = clean_not_provided(val)
    if not clean:
        return None, None

    s = str(clean).strip().upper()
    # Already 3 letters: verify or pass through
    if len(s) == 3 and s.isalpha():
        return s, None

    # Check 2-letter code
    if len(s) == 2 and s in ISO2_TO_ISO3:
        return ISO2_TO_ISO3[s], None

    # Check full name
    if s in ISO3_COUNTRY_MAP:
        return ISO3_COUNTRY_MAP[s], None

    # Try matching without punctuation
    normalized = re.sub(r"[^A-Z ]", "", s)
    if normalized in ISO3_COUNTRY_MAP:
        return ISO3_COUNTRY_MAP[normalized], None

    # Unrecognized country: do not guess!
    return None, f"UNKNOWN_COUNTRY_CODE: '{val}'"


def convert_dropdown(category: str, val: Any) -> tuple[str | None, str | None]:
    """Convert dropdown string based on category dictionary.

    Returns: (mapped_value, warning_code)
    """
    clean = clean_not_provided(val)
    if not clean:
        return None, None

    key = str(clean).strip().lower()
    mapping = DROPDOWN_MAPS.get(category, {})

    if key in mapping:
        return mapping[key], None

    # If exact case-insensitive match not found, check if it matches valid target
    valid_targets = set(mapping.values())

    for target in valid_targets:
        if target.lower() == key:
            return target, None

    return None, f"UNKNOWN_DROPDOWN_VALUE: category '{category}' value '{val}'"


def convert_us_date(val: Any) -> tuple[str | None, str | None]:
    """Convert date or date string to US Date Format (MM/DD/YYYY).

    Returns: (formatted_date_string, warning_code)
    """
    clean = clean_not_provided(val)
    if not clean:
        return None, None

    if isinstance(val, (datetime, date)):
        return val.strftime("%m/%d/%Y"), None

    s = str(clean).strip()
    # If date string like 1971-05-28 or 1971-05-28 00:00:00
    date_patterns = [
        r"^(\d{4})-(\d{1,2})-(\d{1,2})",  # YYYY-MM-DD
        r"^(\d{1,2})/(\d{1,2})/(\d{4})",  # MM/DD/YYYY or DD/MM/YYYY
        r"^(\d{1,2})-(\d{1,2})-(\d{4})",  # MM-DD-YYYY or DD-MM-YYYY
    ]

    for pat in date_patterns:
        m = re.match(pat, s)
        if m:
            p1, p2, p3 = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                if p1 > 1000:  # YYYY-MM-DD
                    dt = date(p1, p2, p3)
                elif p3 > 1000:  # Assume MM/DD/YYYY unless p1 > 12
                    month = p1 if p1 <= 12 else p2
                    day = p2 if p1 <= 12 else p1
                    dt = date(p3, month, day)
                else:
                    break
                return dt.strftime("%m/%d/%Y"), None
            except ValueError as exc:
                return None, f"INVALID_DATE: '{val}' ({exc})"

    return None, f"DATE_PARSE_ERROR: '{val}' could not be parsed to MM/DD/YYYY"

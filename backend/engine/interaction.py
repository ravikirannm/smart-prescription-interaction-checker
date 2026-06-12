import logging
logger = logging.getLogger(__name__)
import requests

SEVERITY_MAP = [
    ("contraindicated",  "CONTRAINDICATED"),
    ("do not use",       "CONTRAINDICATED"),
    ("avoid",            "HIGH"),
    ("serious",          "HIGH"),
    ("severe",           "HIGH"),
    ("caution",          "MODERATE"),
    ("monitor",          "MODERATE"),
    ("may increase",     "MODERATE"),
    ("may decrease",     "MODERATE"),
    ("interaction",      "LOW"),
]

def map_severity(text: str) -> str:
    if not text:
        return "NONE"
    text_lower = text.lower()
    for keyword, severity in SEVERITY_MAP:
        if keyword in text_lower:
            return severity
    return "LOW"


def resolve_rxcui(drug_name: str) -> str | None:
    try:
        resp = requests.get(
            "https://rxnav.nlm.nih.gov/REST/rxcui.json",
            params={"name": drug_name, "search": 1},
            timeout=5
        )
        ids = resp.json().get("idGroup", {}).get("rxnormId", [])
        return ids[0] if ids else None
    except Exception as e:
        logger.warning(f"RxCUI resolve failed for {drug_name}: {e}")
        return None


# def fetch_rxnorm_interactions(rxcui: str, drug2_rxcui: str, drug2_name: str) -> dict:
#     result = {
#         "found": False,
#         "severity": "NONE",
#         "description": None,
#         "source": None,
#         "source_url": f"https://rxnav.nlm.nih.gov/REST/interaction/interaction.json?rxcui={rxcui}"
#     }
#     data = None
#     try:
#         resp = requests.get(
#             "https://rxnav.nlm.nih.gov/REST/interaction/interaction.json",
#             params={"rxcui": rxcui},
#             timeout=8
#         )
#         logger.info(f"RxNorm interaction response for {rxcui} and {drug2_name}: {resp.status_code}")
#         data = resp.json()
#         groups = data.get("interactionTypeGroup", [])
#         for group in groups:
#             for itype in group.get("interactionType", []):
#                 for pair in itype.get("interactionPair", []):
#                     concepts = pair.get("interactionConcept", [])
#                     rxcuis_in_pair = []
#                     for concept in concepts:
#                         min_concept = concept.get("minConceptItem", {})
#                         rxcuis_in_pair.append(min_concept.get("rxcui", ""))
#                     if drug2_rxcui in rxcuis_in_pair:
#                         description = pair.get("description", "")
#                         result["found"] = True
#                         result["description"] = description
#                         result["severity"] = map_severity(description)
#                         result["source"] = group.get("sourceDisclaimer", "RxNorm")
#                         return result
#     except Exception as e:
        
#         logger.warning(f"RxNorm interaction fetch failed: {e}")
#     return result

def map_severity(description: str) -> str:
    """Placeholder for your existing severity mapping logic."""
    description_lower = description.lower()
    if any(w in description_lower for w in ["fatal", "severe", "contraindicated", "avoid"]):
        return "HIGH"
    elif any(w in description_lower for w in ["monitor", "caution", "decrease"]):
        return "MODERATE"
    return "LOW"

def fetch_rxnorm_interactions(rxcui: str, drug2_rxcui: str, drug2_name: str) -> dict:
    result = {
        "found": False,
        "severity": "NONE",
        "description": None,
        "source": "openFDA",
        "source_url": f"https://api.fda.gov/drug/label.json?search=openfda.rxcui.exact:{rxcui}"
    }
    
    try:
        # Query openFDA using the first drug's RxCUI
        resp = requests.get(
            "https://api.fda.gov/drug/label.json",
            params={
                "search": f'openfda.rxcui:"{rxcui}"',
                "limit": 1
            },
            timeout=8
        )
        
        logger.info(f"openFDA response for RxCUI {rxcui}: {resp.status_code}")
        
        if resp.status_code != 200:
            return result
            
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return result
            
        # Extract the structured Drug Interactions section from the FDA label
        # openFDA often returns this as a list containing a single string block
        interaction_sections = results[0].get("drug_interactions", [])
        if not interaction_sections:
            return result
            
        interaction_text = " ".join(interaction_sections)
        
        # Perform a case-insensitive lookup for the second drug's name or RxCUI inside the text block
        # openFDA labels sometimes contain associated RxCUIs in the metadata, but text matching the name is safer for warnings.
        if drug2_name.lower() in interaction_text.lower():
            result["found"] = True
            result["description"] = interaction_text[:1000] + "..." if len(interaction_text) > 1000 else interaction_text
            result["severity"] = map_severity(interaction_text)
            
    except Exception as e:
        logger.warning(f"openFDA interaction fetch failed: {e}")
        
    return result


def fetch_openfda_label(drug_name: str) -> dict:
    result = {
        "warnings": None,
        "boxed_warning": None,
        "drug_interactions_text": None,
        "source_url": f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:\"{drug_name}\"&limit=1"
    }
    try:
        resp = requests.get(
            "https://api.fda.gov/drug/label.json",
            params={"search": f'openfda.generic_name:"{drug_name}"', "limit": 1},
            timeout=8
        )
        data = resp.json()
        results = data.get("results", [])
        if not results:
            # Fallback to brand name search
            resp = requests.get(
                "https://api.fda.gov/drug/label.json",
                params={"search": f'openfda.brand_name:"{drug_name}"', "limit": 1},
                timeout=8
            )
            data = resp.json()
            results = data.get("results", [])
        if results:
            label = results[0]
            result["warnings"] = " ".join(label.get("warnings", []))[:1000] or None
            result["boxed_warning"] = " ".join(label.get("boxed_warning", []))[:500] or None
            result["drug_interactions_text"] = " ".join(label.get("drug_interactions", []))[:1500] or None
    except Exception as e:
        logger.warning(f"OpenFDA label fetch failed for {drug_name}: {e}")
    return result


def fetch_openfda_adverse_events(drug1: str, drug2: str) -> int | None:
    try:
        query = f'patient.drug.medicinalproduct:"{drug1}"+AND+patient.drug.medicinalproduct:"{drug2}"'
        resp = requests.get(
            "https://api.fda.gov/drug/event.json",
            params={"search": query, "count": "serious"},
            timeout=8
        )
        data = resp.json()
        results = data.get("results", [])
        if results:
            return sum(r.get("count", 0) for r in results)
        return 0
    except Exception as e:
        logger.warning(f"OpenFDA adverse event count failed: {e}")
        return None

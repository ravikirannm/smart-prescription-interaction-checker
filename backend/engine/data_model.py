from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class DrugMention(BaseModel):
    name_as_mentioned: str
    generic_name: str = Field(..., description="Generic name of the drug")
    drug_class: str = Field(..., description="Pharmacological class of the drug")
    dosage: str = Field(..., description="Dosage information if available")
    duration: str = Field(..., description="Duration of drug use if available")
    is_pharmaceutical: bool = Field(..., description="Indicates if the mention is a pharmaceutical drug or a non-pharmaceutical substance")
    candidate_names: List[str] = Field(default_factory=list, description="3-5 name variants for robust lookup: brand name, INN, generic name, molecule name, common abbreviations")

class ClinicalReformulation(BaseModel):
    variant: int
    style: str
    clinical_presentation: str
    drugs_involved: str 
    interaction_concern: str
    patient_context: str

class DrugExtractionResult(BaseModel):
    drugs_mentioned: List[DrugMention]
    clinical_reformulations: List[ClinicalReformulation]
    substances_to_verify: List[str]

class PubMedConfig(BaseModel):
    primary_query: str
    fallback_query: str
    filters: List[str]

class EvidenceLevelEnum(str, Enum):
    fda_approved = "FDA-approved"
    evidence_based_supplement = "evidence-based supplement"
    insufficient_evidence = "insufficient evidence"
    no_credible_evidence = "no credible evidence"

class PseudoscienceEvaluation(BaseModel):
    substance: str
    is_pharmaceutical: bool
    evidence_level: EvidenceLevelEnum
    mechanism_known: bool
    reasoning: str
    flagged_as_pseudoscience: bool

class EvidenceQualityEnum(str, Enum):
    high = "high"
    moderate = "moderate"
    low = "low"
    insufficient = "insufficient"

class PICOResult(BaseModel):
    population: Optional[str] = None
    intervention: Optional[str] = None
    comparison: Optional[str] = None
    outcome: Optional[str] = None
    evidence_quality: EvidenceQualityEnum = EvidenceQualityEnum.insufficient
    key_findings: Optional[str] = None
    supporting_pmids: List[str] = Field(default_factory=list)

class ICD11Config(BaseModel):
    search_terms: List[str]

class MedicalCorpusInput(BaseModel):
    pubmed: PubMedConfig
    icd11: ICD11Config

class LikelihoodEnum(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"

# --- NESTED MODELS ---
class Condition(BaseModel):
    name: str = Field(..., description="Name of the medical condition")
    icd11_code: str = Field(..., description="Official ICD-11 diagnostic code")
    likelihood: LikelihoodEnum
    reasoning: str = Field(..., description="Explanation of why this fits the patient data")
    supporting_evidence: str = Field(..., description="Reference to medical textbooks or PubMed papers")

class FollowUp(BaseModel):
    question: str
    purpose: str = Field(..., description="Clinical reasoning for asking this question")

class RedFlag(BaseModel):
    symptom: str
    action: str = Field(..., description="Immediate clinical response required")

class Test(BaseModel):
    test: str
    reason: str = Field(..., description="Differential diagnosis utility of the test")

# --- MAIN RESPONSE MODEL ---
class SymptomAnalysisResponse(BaseModel):
    possible_conditions: List[Condition]
    follow_up_questions: List[FollowUp]
    red_flags: List[RedFlag]
    recommended_tests: List[Test]
   
class StringListResponse(BaseModel):
    items: List[str]

class DrugMappingResponse(BaseModel):
    # Dict[key_type, value_type] handles arbitrary/dynamic dictionary keys flawlessly
    brand_molecule_map: dict[str, str]
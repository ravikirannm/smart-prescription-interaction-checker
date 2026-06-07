from pydantic import BaseModel, Field
from typing import List
from enum import Enum

class DrugMention(BaseModel):
    name_as_mentioned: str
    generic_name: str = Field(..., description="Generic name of the drug")
    drug_class: str = Field(..., description="Pharmacological class of the drug")
    dosage: str = Field(..., description="Dosage information if available")
    duration: str = Field(..., description="Duration of drug use if available")
    is_pharmaceutical: bool = Field(..., description="Indicates if the mention is a pharmaceutical drug or a non-pharmaceutical substance")

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
   
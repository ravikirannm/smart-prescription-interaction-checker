export interface PubmedResult {
    id: string;
    pub_date: string;
    source: string;
    title: string;
}

export interface ICD11Result {
    code: string;
    description: string;
}

export interface SymptomAnalysis {
    follow_up_questions: { purpose: string; question: string }[];
    possible_conditions: {
        icd11_code: string;
        likelihood: string;
        name: string;
        reasoning: string;
        supporting_evidence: string;
    }[];
    recommended_tests: { reason: string; test: string }[];
    red_flags: { action: string; symptom: string }[];
}

export interface SourceLink {
    label: string;
    type: string;
    url: string;
}

export interface InteractionResult {
    drug1: string;
    drug2: string;
    drug1_rxcui: string | null;
    drug2_rxcui: string | null;
    interaction_found: boolean;
    severity: 'NONE' | 'LOW' | 'MODERATE' | 'HIGH' | 'CONTRAINDICATED';
    openfda_boxed_warning: string | null;
    openfda_warnings: string | null;
    rxnorm_description: string | null;
    rxnorm_source: string | null;
    adverse_event_count: number;
    pubmed_abstracts: string[];
    pico: any | null;
}

export interface PseudoscienceFlag {
    flagged: boolean;
    substance: string;
    reason: string;
    evidence_level: string;
    recommendation: string;
    mechanism_known: boolean;
}

export interface VerifiedDrug {
    name_as_mentioned: string;
    generic_name: string;
    drug_class: string;
    dosage: string;
    duration: string;
    rxcui: string | null;
    is_pharmaceutical: boolean;
}

export interface FetchAnalysisResponse {
    all_sources: SourceLink[];
    interaction_results: InteractionResult[];
    pseudoscience_flags: PseudoscienceFlag[];
    verified_drugs: VerifiedDrug[];
    drugs_extracted: {
        drugs_mentioned: VerifiedDrug[];
        clinical_reformulations: string[];
        substances_to_verify: string[];
    };
    query_response: string;
}
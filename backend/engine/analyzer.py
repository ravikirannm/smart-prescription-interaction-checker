# Use Ollama qwen3.5:9b for symptom analysis
import ollama
from constants import OLLAMA_MODEL, OLLAMA_URL
import logging
import json
import threading
import requests
from Bio import Entrez,Medline
from ddgs import DDGS
import re
from itertools import combinations
import xml.etree.ElementTree as ET
import concurrent.futures

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

from .data_model import DrugExtractionResult, MedicalCorpusInput, SymptomAnalysisResponse, PseudoscienceEvaluation, PubMedConfig, PICOResult, StringListResponse,DrugMappingResponse
from .interaction import map_severity, resolve_rxcui, fetch_rxnorm_interactions, fetch_openfda_label, fetch_openfda_adverse_events
from .database import DBManager
from .memory import ConversationMemory


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
class PresciptionInteractionChecker:
    def __init__(self):
        # Initialize any necessary variables or configurations here
        self.client = ollama.Client(host=OLLAMA_URL)
        self.db_manager = DBManager()
        

    def interaction_check(self, user_query,user_id, thread_id=None):
        # 0. Initialize Memory
        yield {"type": "progress", "thread_id": thread_id, "message": "Initializing reasoning engine..."}

        memory = ConversationMemory(self.db_manager, user_id, thread_id)
        memory._ensure_thread() # Ensure thread exists in DB
        ctx = memory.get_working_context()
        # Build context string for prompts
        history_str = ctx['history']
        shared_str = json.dumps(ctx['shared_memory'], indent=1)
        thread_str = json.dumps(ctx['thread_memory'], indent=1)

        # 1. Pass 1: Use LLM with search tool to extract molecule present in the drug brand
        yield {"type": "progress", "thread_id": thread_id, "message": "Identifying active molecules in drug brands..."}

        step_a_system_prompt = """
            You are a drug name extractor.

            The user will provide a medical query containing drug brand names, generic names, or both.

            Your job:
            1. Identify every drug brand name and generic name mentioned in the query.
            2. Output ONLY a JSON array of strings — one entry per drug, exactly as mentioned.

            Example input: "Calpol 500, Brufen 400mg and metformin"
            Example output: ["Calpol 500", "Brufen 400mg", "metformin"]

            No explanation. No preamble. Only the JSON array.
        """

        messages = [
            {"role": "system", "content": step_a_system_prompt},
            {"role": "user", "content": user_query}
        ]
        pass1_response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            format=StringListResponse.model_json_schema(),
            options={"temperature": 0.1}
        )
        validated_data = StringListResponse.model_validate_json(pass1_response.message.content)
        drug_names = validated_data.items
        brand_molecule_map = {}
        for item in drug_names:
            content = self.search_tool(f"Molecule present in the medical drug {item}")
            brand_molecule_map[item] = content.strip()

        
        logger.info(f"Initial drug name extraction: {brand_molecule_map}")

        step_b_system_prompt = """
            You are a pharmaceutical ingredient extractor.

            You will be given:
            1. A list of drug names to resolve.
            2. Web search results for each drug.

            Your job:
            - Read the search results carefully for each drug.
            - Identify the active pharmaceutical ingredient (API) or generic molecule name.
            - If multiple active ingredients exist (combination drug), list all separated by " + ".
            - If the search results do not clearly name the active ingredient, output null for that drug.

            Rules:
            - Use ONLY the search results provided. Do not use prior knowledge.
            - Match each drug name exactly as given in the input list.
            - Output ONLY this JSON:

            {
                "brand_molecule_map": {
                    "<drug_name_as_given>": "<active_molecule_or_drug_name_as_given>"
                },
            }

            No preamble. No explanation. Only JSON.
        """

        step_b_messages = [
            {"role": "system", "content": step_b_system_prompt},
            {
                "role": "user",
                "content": (
                    f"Drugs to resolve: {json.dumps(drug_names)}\n\n"
                    f"Search results:\n\n{json.dumps(brand_molecule_map, indent=1)}"
                )
            },
          
        ]
        step_b_response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=step_b_messages,
            format=DrugMappingResponse.model_json_schema(),
            options={"temperature": 0.1}
        )
        validated_data = DrugMappingResponse.model_validate_json(step_b_response.message.content)
        brand_molecule_map = validated_data.brand_molecule_map
        logger.info(f"Validated brand to molecule mapping: {brand_molecule_map}")
        for k,v in brand_molecule_map.items():
            if v is None or v.strip() == "" or v == 'null':
                brand_molecule_map[k] = k # Fallback to as-mentioned if LLM fails to extract
        user_query =  user_query + "\n\nBrand to molecule mapping:\n" + json.dumps(brand_molecule_map, indent=1)
        
        

        # 2. Pass 2: Clinical Reformulation
        yield {"type": "progress", "thread_id": thread_id, "message": "Structuring clinical presentation..."}

        system_prompt = f"""
            You are a clinical pharmacology language formatter. Your only job is to:
            1. Extract all drug and substance names from the patient's natural language input
            2. Generate 3 structured clinical reformulations focused on drug interaction risk
            3. Flag any substance that appears non-pharmaceutical for pseudoscience verification

            ==== SHARED CONTEXT FROM OTHER CONVERSATIONS ====
            {shared_str}
            ==== WORKING MEMORY CONTEXT FROM CURRENT CONVERSATION ====
            {thread_str}

            Rules:
            - Extract ALL substances mentioned — brand names, generic names, supplements, herbal remedies
            - Do not add drugs not mentioned by the patient
            - Do not diagnose or speculate on conditions
            - If dosage/duration is unclear, mark as "unspecified"
            - Each reformulation must use a different clinical framing style
            - Output must be valid JSON only, no preamble, no explanation
            - For each drug in drugs_mentioned, populate candidate_names with 3-5 name variants:
              the name as mentioned, INN/generic name, molecule name, common abbreviations, and
              chemical synonyms — these are used to maximize hits against drug databases like RxNorm

            Reformulation styles:
            1. Standard clinical — formal pharmacological note style, generic drug names, mechanism class
            2. Interaction-risk — frame around known risk categories (anticoagulation, CNS, hepatotoxicity etc.)
            3. Mechanism-focused — describe each drug by its pharmacological mechanism and receptor targets

            Output format (strict JSON):
            {{
                "drugs_mentioned": [
                    {{
                        "name_as_mentioned": "aspirin",
                        "generic_name": "acetylsalicylic acid",
                        "drug_class": "NSAID / antiplatelet",
                        "dosage": "unspecified",
                        "duration": "unspecified",
                        "is_pharmaceutical": true,
                        "candidate_names": ["aspirin", "acetylsalicylic acid", "ASA", "acetylsalicylate", "2-acetoxybenzoic acid"]
                    }}
                ],
                "reformulations": [
                    {{
                        "variant": 1,
                        "style": "Standard Clinical",
                        "clinical_presentation": "",
                        "drugs_involved": [],
                        "interaction_concern": "",
                        "patient_context": ""
                    }},
                    {{
                        "variant": 2,
                        "style": "Interaction-Risk",
                        "clinical_presentation": "",
                        "drugs_involved": [],
                        "interaction_concern": "",
                        "patient_context": ""
                    }},
                    {{
                        "variant": 3,
                        "style": "Mechanism-Focused",
                        "clinical_presentation": "",
                        "drugs_involved": [],
                        "interaction_concern": "",
                        "patient_context": ""
                    }}
                ]
            }}
           
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
           
        ]
        for turn in history_str:
            messages.append({"role": 'user', "content": turn['query']})
            messages.append({"role": "assistant", "content": json.dumps(turn['analysis'], indent=1)})
        messages.append({"role": "user", "content": user_query})
        logger.info(f"Analyzing medications: {user_query}")
        response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            format=DrugExtractionResult.model_json_schema(), # Force JSON structure
            options={'temperature': 0.2,"web_search": True, "web_search_num_results": 5} # Low temperature for medical accuracy
        )
        drug_extraction_result = DrugExtractionResult.model_validate_json(response['message']['content'])
        drug_extraction_result = drug_extraction_result.model_dump() # Convert to dict for easier manipulation in next steps

        yield {"type": "progress", "thread_id": thread_id, "message": "Verifying substances against evidence base..."}

        logger.info(f"Drug extraction result: {drug_extraction_result}")

        pseudoscience_flags = []
        verified_drugs = []

        for drug in drug_extraction_result.get("drugs_mentioned", []):
            drug_name = drug.get("name_as_mentioned", "")

            # Build candidate list: LLM-generated variants + generic name + as-mentioned fallback
            candidates = list(drug.get("candidate_names") or [])
            for fallback in [drug.get("generic_name", ""), drug_name]:
                if fallback and fallback not in candidates:
                    candidates.append(fallback)
            seen_lower: set = set()
            unique_candidates = [
                c for c in candidates
                if c and not (c.lower() in seen_lower or seen_lower.add(c.lower()))
            ]

            # Try each candidate name against RxNorm — first hit wins
            rxnorm_verified = False
            rxcui_found = None
            matched_candidate = None

            for candidate in unique_candidates:
                try:
                    rxnorm_resp = requests.get(
                        "https://rxnav.nlm.nih.gov/REST/rxcui.json",
                        params={"name": candidate, "search": 1},
                        timeout=5
                    )
                    rxcui = rxnorm_resp.json().get("idGroup", {}).get("rxnormId", [])
                    if rxcui:
                        rxnorm_verified = True
                        rxcui_found = rxcui[0]
                        matched_candidate = candidate
                        break
                except Exception as e:
                    logger.warning(f"RxNorm lookup failed for '{candidate}': {e}")

            if rxnorm_verified:
                drug["rxcui"] = rxcui_found
                verified_drugs.append(drug)
                logger.info(f"RxNorm verified '{drug_name}' via '{matched_candidate}' → rxcui={rxcui_found}")
                continue

            # All candidates missed RxNorm — run LLM pseudoscience check as fallback
            llm_prompt = f"""
                You are a pharmacology expert and scientific skeptic.
                Evaluate the substance below and determine whether it is a legitimate pharmaceutical drug.

                Substance: "{drug_name}"

                Respond in strict JSON only. No preamble. No explanation outside the JSON.

                {{
                    "substance": "{drug_name}",
                    "is_pharmaceutical": true or false,
                    "evidence_level": "FDA-approved" | "evidence-based supplement" | "insufficient evidence" | "no credible evidence",
                    "mechanism_known": true or false,
                    "reasoning": "brief one-sentence scientific explanation",
                    "flagged_as_pseudoscience": true or false
                }}

                Rules:
                - is_pharmaceutical is true ONLY if the substance has an established pharmacological mechanism
                and is recognized by a regulatory body (FDA, EMA, etc.)
                - flagged_as_pseudoscience is true if the substance is homeopathic, has no measurable
                active compound, or has no credible peer-reviewed evidence of pharmacological activity
                - Do not flag evidence-based herbal supplements (e.g. melatonin, St. John's Wort)
                as pseudoscience — mark them as "evidence-based supplement" and is_pharmaceutical=false
                - Homeopathic preparations (any dilution like 6C, 30C, 200C) are always pseudoscience
            """

            llm_response = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": llm_prompt},
                    {"role": "user", "content": f"Evaluate: {drug_name}"}
                ],
                format=PseudoscienceEvaluation.model_json_schema(),
                options={"temperature": 0, "web_search": True, "web_search_num_results": 5}
            )

            try:
                llm_result = PseudoscienceEvaluation.model_validate_json(
                    llm_response["message"]["content"]
                ).model_dump()
            except Exception:
                logger.warning(f"LLM pseudoscience response parse failed for '{drug_name}'")
                llm_result = {"flagged_as_pseudoscience": False, "is_pharmaceutical": True}

            if llm_result.get("flagged_as_pseudoscience", False):
                pseudoscience_flags.append({
                    "flagged": True,
                    "substance": drug_name,
                    "reason": llm_result.get("reasoning", "No credible pharmacological evidence found."),
                    "evidence_level": llm_result.get("evidence_level", "no credible evidence"),
                    "mechanism_known": llm_result.get("mechanism_known", False),
                    "recommendation": (
                        "No drug interaction analysis is possible for this substance. "
                        "It has no recognized pharmaceutical identity in RxNorm and no "
                        "established pharmacological mechanism. Please consult a pharmacist "
                        "about evidence-based alternatives."
                    )
                })
                logger.info(f"Pseudoscience flagged: '{drug_name}'")
            else:
                # LLM confirms it's a real drug despite RxNorm miss — accept without rxcui
                verified_drugs.append({**drug, "rxcui": None})
                logger.info(f"'{drug_name}' accepted via LLM fallback despite RxNorm miss")

        logger.info(f"Verified drugs: {[d['name_as_mentioned'] for d in verified_drugs]}")
        logger.info(f"Pseudoscience flags: {[f['substance'] for f in pseudoscience_flags]}")

        yield {"type": "progress", "thread_id": thread_id, "message": "Checking drug interactions and gathering evidence..."}

        drug_rxcui_map = {}
        for drug in verified_drugs:
            name = drug.get("generic_name") or drug.get("name_as_mentioned")
            rxcui = drug.get("rxcui") or resolve_rxcui(name)
            drug_rxcui_map[name] = rxcui
            drug["rxcui"] = rxcui

        logger.info(f"Resolved RxCUIs: {drug_rxcui_map}")

        # --- Process all drug pairs ---
        drug_names = list(drug_rxcui_map.keys())
        drug_pairs = list(combinations(drug_names, 2))

        interaction_results = []
        all_sources = []

        for drug1_name, drug2_name in drug_pairs:
            rxcui1 = drug_rxcui_map.get(drug1_name)
            rxcui2 = drug_rxcui_map.get(drug2_name)

            pair_result = {
                "drug1": drug1_name,
                "drug2": drug2_name,
                "drug1_rxcui": rxcui1,
                "drug2_rxcui": rxcui2,
                "interaction_found": False,
                "severity": "NONE",
                "rxnorm": {},
                "openfda_drug1": {},
                "openfda_drug2": {},
                "adverse_event_count": None,
                "combined_severity": "NONE",
                "sources": []
            }

            # Run RxNorm + OpenFDA concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = {}

                if rxcui1 and rxcui2:
                    futures["rxnorm"] = executor.submit(
                        fetch_rxnorm_interactions, rxcui1, rxcui2, drug2_name
                    )

                futures["openfda_d1"] = executor.submit(fetch_openfda_label, drug1_name)
                futures["openfda_d2"] = executor.submit(fetch_openfda_label, drug2_name)
                futures["adverse"]    = executor.submit(fetch_openfda_adverse_events, drug1_name, drug2_name)

                rxnorm_data   = futures["rxnorm"].result()   if "rxnorm"    in futures else {}
                openfda_d1    = futures["openfda_d1"].result()
                openfda_d2    = futures["openfda_d2"].result()
                adverse_count = futures["adverse"].result()

            # Severity: take worst across all sources
            severities = ["NONE", "LOW", "MODERATE", "HIGH", "CONTRAINDICATED"]

            rxnorm_severity = rxnorm_data.get("severity", "NONE")

            # Derive severity from OpenFDA drug_interactions text mentioning the other drug
            openfda_text = ""
            if openfda_d1.get("drug_interactions_text"):
                if drug2_name.lower() in openfda_d1["drug_interactions_text"].lower():
                    openfda_text = openfda_d1["drug_interactions_text"]
            if not openfda_text and openfda_d2.get("drug_interactions_text"):
                if drug1_name.lower() in openfda_d2["drug_interactions_text"].lower():
                    openfda_text = openfda_d2["drug_interactions_text"]

            openfda_severity  = map_severity(openfda_text)
            boxed_severity    = map_severity(
                (openfda_d1.get("boxed_warning") or "") + " " + (openfda_d2.get("boxed_warning") or "")
            )

            combined_severity = max(
                [rxnorm_severity, openfda_severity, boxed_severity],
                key=lambda s: severities.index(s)
            )

            pair_result.update({
                "interaction_found": rxnorm_data.get("found", False) or openfda_severity != "NONE",
                "severity": combined_severity,
                "rxnorm": rxnorm_data,
                "openfda_drug1": openfda_d1,
                "openfda_drug2": openfda_d2,
                "adverse_event_count": adverse_count,
                "combined_severity": combined_severity,
            })

            # Collect source links for right pane
            sources = []
            if rxnorm_data.get("source_url"):
                sources.append({
                    "label": f"RxNorm: {drug1_name} ↔ {drug2_name}",
                    "url": rxnorm_data["source_url"],
                    "type": "rxnorm"
                })
            if openfda_d1.get("source_url"):
                sources.append({
                    "label": f"OpenFDA Label: {drug1_name}",
                    "url": openfda_d1["source_url"],
                    "type": "openfda"
                })
            if openfda_d2.get("source_url"):
                sources.append({
                    "label": f"OpenFDA Label: {drug2_name}",
                    "url": openfda_d2["source_url"],
                    "type": "openfda"
                })

            pair_result["sources"] = sources
            all_sources.extend(sources)
            interaction_results.append(pair_result)

            logger.info(
                f"Pair {drug1_name} ↔ {drug2_name}: "
                f"found={pair_result['interaction_found']}, severity={combined_severity}"
            )

    

        # Pass 5 — PubMed Retrieval + LLM PICO Generation
        yield {"type": "progress", "thread_id": thread_id, "message": "Retrieving PubMed evidence and generating PICO..."}
        
        pubmed_results_by_pair = {}

        for pair in interaction_results:
            drug1 = pair["drug1"]
            drug2 = pair["drug2"]
            pair_key = f"{drug1}|{drug2}"

            # Step 1: LLM builds MeSH query
            query_obj = self.build_pubmed_query(drug1, drug2, drug_extraction_result.get("reformulations", []))

            # Step 2: ESearch with primary query
            pmids = self.esearch_pubmed(query_obj["primary_query"], query_obj.get("filters", []))

            # Step 3: Fallback if primary returns nothing
            if not pmids:
                logger.info(f"Primary PubMed query empty for {drug1}+{drug2}, trying fallback")
                pmids = self.esearch_pubmed(query_obj["fallback_query"], [])

            # Step 4: EFetch abstracts
            abstracts = self.efetch_abstracts(pmids)
            logger.info(f"PubMed: {len(abstracts)} abstracts retrieved for {drug1} + {drug2}")

            # Step 5: LLM PICO extraction from real abstract text
            pico = self.generate_pico_from_abstracts(drug1, drug2, abstracts, shared_str, thread_str)

            # Attach to pair result
            pair["pubmed_abstracts"] = abstracts
            pair["pico"] = pico

            # Add PubMed source links for right pane
            for abstract in abstracts:
                all_sources.append({
                    "label": f"PubMed: {abstract['title'][:60]}...",
                    "url": abstract["url"],
                    "type": "pubmed",
                    "pmid": abstract["pmid"]
                })

            pubmed_results_by_pair[pair_key] = {
                "query_used": query_obj,
                "pmids_found": pmids,
                "abstracts": abstracts,
                "pico": pico
            }

            logger.info(
                f"PICO for {drug1} + {drug2}: "
                f"{'generated' if pico else 'null — insufficient evidence'}"
            )

        # Pass 6 — Synthesis + Streaming
        yield {"type": "progress", "thread_id": thread_id, "message": "Synthesizing clinical assessment..."}

        # Assemble structured result object
        response_data = {
            "drugs_extracted": drug_extraction_result,
            "brand_molecule_map": brand_molecule_map,
            "pseudoscience_flags": pseudoscience_flags,
            "verified_drugs": verified_drugs,
            "interaction_results": [
                {
                    "drug1": pair["drug1"],
                    "drug2": pair["drug2"],
                    "drug1_rxcui": pair["drug1_rxcui"],
                    "drug2_rxcui": pair["drug2_rxcui"],
                    "interaction_found": pair["interaction_found"],
                    "severity": pair["combined_severity"],
                    "rxnorm_description": pair.get("rxnorm", {}).get("description"),
                    "rxnorm_source": pair.get("rxnorm", {}).get("source"),
                    "openfda_warnings": pair.get("openfda_drug1", {}).get("warnings"),
                    "openfda_boxed_warning": pair.get("openfda_drug1", {}).get("boxed_warning"),
                    "adverse_event_count": pair.get("adverse_event_count"),
                    "pico": pair.get("pico"),
                    "pubmed_abstracts": pair.get("pubmed_abstracts", []),
                }
                for pair in interaction_results
            ],
            "all_sources": all_sources,
        }

        # Build synthesis prompt with full evidence context
        chat_prompt = f"""
            You are an expert clinical pharmacology assistant.
            You have gathered comprehensive drug interaction data from multiple authoritative sources.
            Your job is to explain the findings to the patient in clear, compassionate language.
            Do not dumb down medical accuracy — the patient deserves honest information.
            Never give a definitive diagnosis or treatment recommendation.
            Always advise consulting a pharmacist or prescribing physician.

            ==== SHARED CONTEXT FROM OTHER CONVERSATIONS ====
            {shared_str}
            ==== WORKING MEMORY CONTEXT FROM CURRENT CONVERSATION ====
            {thread_str}

            ==== INTERACTION ANALYSIS ====
            {json.dumps(response_data["interaction_results"], indent=1)}

            ==== PSEUDOSCIENCE FLAGS ====
            {json.dumps(pseudoscience_flags, indent=1)}

            Structure your response as follows:
            1. Brief acknowledgment of what the patient described
            2. For each drug pair — explain the interaction risk in plain language, severity, and what it means practically
            3. If any pseudoscience flags exist — explain calmly and factually why that substance cannot be analyzed
            4. Key takeaways and next steps (consult pharmacist, watch for specific symptoms)
            5. Red flags — specific symptoms that should prompt immediate medical attention

            Tone: warm, clear, never alarmist. Scientific but human.
        """

        stream_response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": chat_prompt},
                {"role": "user", "content": user_query}
            ],
            stream=True,
            options={"temperature": 0.4}
        )

        full_query_response = ""
        for chunk in stream_response:
            token = chunk['message']['content']
            full_query_response += token
            yield {"type": "chat_stream", "token": token}

        response_data["query_response"] = full_query_response

        # Memory update in background — does not block stream
        memory_thread = threading.Thread(
            target=self.make_history_updates,
            args=(response_data, user_query, memory, shared_str, thread_str)
        )
        memory_thread.start()

        yield {"type": "done", "data": response_data}
     

    def make_history_updates(self,response_data, user_query, memory: ConversationMemory, shared_str: str, thread_str: str):
        
        full_history = memory.fetch_thread_history()
        system_prompt_summarize_thread = f"""
            You are a conversation summarizer for a drug interaction checking tool.
            Summarize ONLY what is explicitly present in the conversation.
            Do NOT invent symptoms, diagnoses, or patient history not present in the input.
            Current thread context: {thread_str if thread_str else "None."}
        """

        messages = [{"role": "system", "content": system_prompt_summarize_thread}]

        for turn in full_history:
            if turn['role'] == 'user':
                messages.append({"role": "user", "content": turn['content']})
            else:
                # Only pass readable parts — not raw JSON
                prior_response = turn['content'].get('query_response', '')
                prior_interactions = turn['content'].get('interaction_results', [])
                readable = prior_response + "\n\nInteraction findings:\n" + "\n".join(
                    f"- {ix['drug1']} + {ix['drug2']}: severity={ix['severity']}"
                    for ix in prior_interactions
                )
                messages.append({"role": "assistant", "content": readable})

        # Current turn
        messages.append({"role": "user", "content": user_query})

        current_readable = response_data.get('query_response', '')
        current_interactions = response_data.get('interaction_results', [])
        current_readable += "\n\nInteraction findings:\n" + "\n".join(
            f"- {ix['drug1']} + {ix['drug2']}: severity={ix['severity']}, "
            f"interaction_found={ix['interaction_found']}"
            for ix in current_interactions
        )
        messages.append({"role": "assistant", "content": current_readable})

        # Summarization instruction as user turn (not system)
        messages.append({"role": "user", "content": (
            "Write a concise clinical summary of this drug interaction check. "
            "Include: drugs queried, interaction findings, unverifiable substances, and key takeaways. "
            "Summarize only what is in the conversation. Do not add diagnoses or symptoms."
        )})
        # Create basic model response for thread summary        
        summary_response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            options={"temperature": 0.5}
        )
        thread_summary = summary_response['message']['content'].strip()
        logger.info(f"Generated thread summary: {thread_summary}")
        memory.save_to_memory("summary", thread_summary, shared=False)
        system_prompt_summarize_shared = f"""
            You are a pharmacological pattern accumulator for a prescription drug interaction tool.
            Your role is to distill reusable clinical pharmacology signal from session summaries.
            You do NOT store anything about individual patients.

            Current accumulated intelligence:
            {shared_str if shared_str else "None yet."}

            Rules:
            - Extract ONLY from the session summary provided below.
            - Do NOT generate observations from prior training knowledge.
            - If the session contains no new generalizable signal, return existing intelligence unchanged.
            - No patient identifiers, demographics, or individual case details.
            - One observation per line. Specific over generic.

            Extract only what generalizes across patients:
            - Drug co-prescription patterns and associated risk profiles
            - Brand name ambiguities or resolution failures (wrong molecule identified)
            - Drug class combinations with clinical significance
            - Unverifiable or unrecognized substances encountered
            - Interaction severity patterns worth tracking across similar regimens
            - Generate only text without JSON reponse
            """.strip()

        messages = [
            {"role": "system", "content": system_prompt_summarize_shared},
            {
                "role": "user",
                "content": (
                    f"Session summary:\n\n{thread_summary}\n\n"
                    "Update the accumulated intelligence based strictly on the above. "
                    "Do not add observations absent from this session."
                )
            }
        ]
    
        shared_summary_response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            options={"temperature": 0.5}
        )
        
        shared_summary = shared_summary_response['message']['content'].strip()
        logger.info(f"Thread summary: {thread_summary}")
        logger.info(f"Shared summary: {shared_summary}")
        memory.save_to_memory("shared_summary", shared_summary, shared=True)
        memory.save_turn(user_query, response_data)
        # Update thread title based on summary
        title_update_prompt = f"""
            You are a thread title generator for a medical symptom analysis tool.
            Based on the following conversation summary, generate a concise and descriptive thread title that captures the main clinical theme of the conversation. The title should be no more than 5 words and should help the user quickly identify the topic of this thread in the future.

            Conversation summary:
            {thread_summary}

            Generate an appropriate thread title:
        """
        title_response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": title_update_prompt},
            ],
            options={"temperature": 0.5}
        )
        new_title = title_response['message']['content'].strip()
        if new_title:
            logger.info(f"Updating thread title to: {new_title}")
            memory.update_thread_title(new_title)

        




    def build_pubmed_query(self, drug1: str, drug2: str, reformulations: list) -> dict:
        """Use LLM to build MeSH boolean query — same pattern as EBSA Pass 3."""
        interaction_concerns = [
            r.get("interaction_concern", "")
            for r in reformulations
            if r.get("interaction_concern")
        ]

        prompt = f"""
            You are a medical literature search specialist.
            Generate optimized PubMed search queries for the drug interaction between {drug1} and {drug2}.

            === INTERACTION CONCERNS FROM CLINICAL REFORMULATION ===
            {json.dumps(interaction_concerns, indent=1)}

            Output strict JSON only. No preamble. No explanation.

            {{
                "primary_query": "most specific MeSH boolean query",
                "fallback_query": "broader query if primary returns no results",
                "filters": ["Journal Article", "Clinical Trial", "Review"]
            }}

            Rules:
            - Use MeSH terms with [MeSH Terms] tag where possible
            - Use AND/OR/NOT boolean operators
            - primary_query must include both drug names and interaction/adverse effects
            - fallback_query uses generic names only without MeSH tags
            - Do not add conditions not implied by the interaction concern
        """
        response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Build PubMed query for: {drug1} AND {drug2}"}
            ],
            format=PubMedConfig.model_json_schema(),
            options={"temperature": 0.1}
        )
        try:
            return PubMedConfig.model_validate_json(response["message"]["content"]).model_dump()
        except Exception:
            return {
                "primary_query": f"{drug1}[MeSH Terms] AND {drug2}[MeSH Terms] AND drug interactions[MeSH Terms]",
                "fallback_query": f"{drug1} AND {drug2} AND drug interaction",
                "filters": ["Journal Article"]
            }


    def esearch_pubmed(self,query: str, filters: list, max_results: int = 5) -> list[str]:
        """Returns list of PMIDs."""
        filter_str = " AND ".join(f'"{f}"[Publication Type]' for f in filters)
        full_query = f"({query}) AND ({filter_str})" if filter_str else query
        try:
            resp = requests.get(
                f"{PUBMED_BASE}esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": full_query,
                    "retmax": max_results,
                    "retmode": "json",
                    "sort": "relevance"
                },
                timeout=8
            )
            return resp.json().get("esearchresult", {}).get("idlist", [])
        except Exception as e:
            logger.warning(f"PubMed ESearch failed: {e}")
            return []


    def efetch_abstracts(self, pmids: list[str]) -> list[dict]:
        """Fetch and parse abstracts cleanly using the MEDLINE flat text parser."""
        if not pmids:
            return []
            
        try:
            # Use context manager to guarantee the network socket closes safely
            with Entrez.efetch(
                db="pubmed", 
                id=pmids,  # Entrez accepts a Python list of strings natively
                rettype="medline", 
                retmode="text"
            ) as handle:
                records = list(Medline.parse(handle))
                
            # Map the flat MEDLINE tags to your exact dictionary schema
            articles = []
            for r in records:
                abstract = r.get("AB")
                
                if abstract:  # Maintain your rule to skip articles without an abstract
                    articles.append({
                        "pmid": r.get("PMID", ""),
                        "title": r.get("TI", ""),
                        "journal": r.get("JT", ""),            # Full Journal Title
                        "year": r.get("DP", "")[:4],           # Extracts just the 4-digit year (e.g., '2026')
                        "abstract": abstract[:2000],           # Cap to avoid token/context overflow
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{r.get('PMID')}/"
                    })
            return articles
        except Exception as e:
            logger.warning(f"PubMed MEDLINE EFetch or parse failed: {e}")
            return []


    def generate_pico_from_abstracts(self,
        drug1: str,
        drug2: str,
        abstracts: list[dict],
        shared_str: str,
        thread_str: str
    ) -> dict | None:
        """LLM extracts PICO strictly from retrieved abstract text. No templating."""
        if not abstracts:
            return None

        abstracts_text = "\n\n".join(
            f"[PMID {a['pmid']}] {a['title']} ({a['year']})\n{a['abstract']}"
            for a in abstracts
        )
        logger.info(f"Generating PICO for {drug1} + {drug2} from abstracts: {abstracts_text[:500]}...")  # Log the abstracts being used for PICO generation, truncated for readability
        prompt = f"""
            You are a clinical evidence synthesizer.
            Extract a PICO framework for the drug interaction between {drug1} and {drug2}.
            Base your extraction STRICTLY on the PubMed abstracts provided below.
            Do not invent, infer, or add anything not stated in the abstracts.
            If a PICO element cannot be found in the abstracts, set it to null.

            ==== SHARED CONTEXT FROM OTHER CONVERSATIONS ====
            {shared_str}
            ==== WORKING MEMORY CONTEXT FROM CURRENT CONVERSATION ====
            {thread_str}

            === PUBMED ABSTRACTS ===
            {abstracts_text}

            Output strict JSON only. No preamble. No explanation.

            {{
                "population": "patient population described across the studies, or null",
                "intervention": "the drug combination or co-administration studied, or null",
                "comparison": "comparator arm or condition studied, or null",
                "outcome": "primary outcomes and findings reported, or null",
                "evidence_quality": "high | moderate | low | insufficient",
                "key_findings": "1-2 sentence summary of what the evidence collectively shows",
                "supporting_pmids": ["pmid1", "pmid2"]
            }}

            Rules:
            - Quote or closely paraphrase from the abstracts — do not generalize
            - supporting_pmids must only contain PMIDs from the abstracts above
            - evidence_quality: high = RCT/meta-analysis, moderate = cohort/case-control, 
            low = case report/expert opinion, insufficient = no relevant findings
            - If abstracts contain no relevant interaction data, set all fields to null 
            and evidence_quality to "insufficient"
        """
        logger.info(f"Generating PICO for {drug1} + {drug2} with prompt: {prompt[:500]}...")  # Log the start of PICO generation with a truncated prompt for readability
        response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Extract PICO for {drug1} + {drug2} interaction from the abstracts above."}
            ],
            format=PICOResult.model_json_schema(),
            options={"temperature": 0}  # Zero temp — must stay grounded
        )

        try:
            pico = PICOResult.model_validate_json(response["message"]["content"])
            if (
                pico.evidence_quality == "insufficient"
                and not any([pico.population, pico.intervention, pico.comparison, pico.outcome])
            ):
                return None
            pico_dict = pico.model_dump()
            logger.info(f"PICO generated for {drug1} + {drug2}: {pico_dict}")
            return pico_dict
        except Exception:
            logger.warning(f"PICO parse failed for {drug1} + {drug2}")
            return None

    def search_tool(self, query: str) -> str:
        """Query should be like Molecule present in X Brand"""
        query = re.sub(r"(\d+)\+(\d+)", r"\1/\2", query)

        with DDGS() as ddgs:
            # Adding region and safesearch can help bypass empty results
            results = [r for r in ddgs.text(query, region='us-en', safesearch='off', max_results=5)]
            
            if results:
                context = "\n\n".join([f"Source: {r['title']}\n{r['body']}" for r in results])
            else:
                context = ""
            logger.info(f"Search results for '{query}': {context[:500]}...")  # Log the search query and a snippet of the results
        return context

    
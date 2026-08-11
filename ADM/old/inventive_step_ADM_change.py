"""
Inventive Step ADM 

Last Updated: 06.04.26

Status: Small changes left

Test Coverage: 61%

Version History:
v_1: initial version
v_2: changes the workings from 1.0 to be cleaner, easier to visualise and to understand; logic changes made to ensure better functioning
v_3: more substantial changes and different variations created for more robust testing i.e. ablation parts
v_4: implemented tests and validated ADM correctness
v_5: extracted all question text to questions.json for prompt ablation
v_6: implemented features for switching questions dependent on .json

To Do:
- remove redundant questions
"""

import json
import os
from pathlib import Path
from ADM_Construction import ADM

import logging

logger = logging.getLogger(__name__)

# ── question registry ─────────────────────────────────────────────────────────

_DEFAULT_QUESTIONS_PATH = Path(__file__).parent / "questions.json"
_LOADED_QUESTIONS: dict | None = None


def load_questions(path: str | Path | None = None) -> dict:
    """Load the questions JSON and return it.

    The result is cached on the module.  Pass *path* to override the default
    ``questions.json`` that lives next to this file.  Subsequent calls with no
    *path* return the cached dict; pass a new *path* (or call ``set_questions``)
    to replace it.
    """
    global _LOADED_QUESTIONS
    if path is not None:
        with open(path, encoding="utf-8") as fh:
            _LOADED_QUESTIONS = json.load(fh)
    elif _LOADED_QUESTIONS is None:
        if _DEFAULT_QUESTIONS_PATH.exists():
            with open(_DEFAULT_QUESTIONS_PATH, encoding="utf-8") as fh:
                _LOADED_QUESTIONS = json.load(fh)
        else:
            logger.warning("questions.json not found at %s; using empty dict", _DEFAULT_QUESTIONS_PATH)
            _LOADED_QUESTIONS = {}
    return _LOADED_QUESTIONS

def set_questions(questions: dict) -> None:
    """Replace the module-level questions cache with *questions*.

    Use this when you want to inject a custom questions dict programmatically
    (e.g. from batched_hybrid_system.py after loading --questions_file).
    """
    global _LOADED_QUESTIONS
    _LOADED_QUESTIONS = questions

def _q(questions: dict | None, key: str, fallback: str = "", **fmt) -> str:
    """Look up *key* in *questions* (or the module cache) and return the text.

    If the key is missing, *fallback* is returned so nothing breaks.
    ``**fmt`` kwargs are passed to ``str.format_map`` for feature/problem name
    substitution (e.g. ``feature_name="MyFeature"``).
    """
    src = questions if questions is not None else load_questions()
    entry = src.get(key, {})
    text = entry.get("text", fallback) if isinstance(entry, dict) else str(entry)
    if fmt:
        try:
            text = text.format_map(fmt)
        except (KeyError, ValueError):
            pass
    return text

def adm_initial(questions: dict | None = None):
    """ 
    This ADM asks the user about the initial preconditions required for Inventive Step.

    Args:
        questions: Optional dict loaded from questions.json (or a modified copy for
                   prompt ablation).  If None the module-level cache is used.
    """
    
    adm = ADM("Inventive Step: Preconditions")
    
    # Add information questions before the logic questions
    adm.addInformationQuestion("INVENTION_TITLE",           _q(questions, "INFO_INVENTION_TITLE",           "What is the title of your invention?"))
    adm.addInformationQuestion("INVENTION_DESCRIPTION",     _q(questions, "INFO_INVENTION_DESCRIPTION",     "Please provide a brief description of your invention (max 100 words)"))
    adm.addInformationQuestion("INVENTION_TECHNICAL_FIELD", _q(questions, "INFO_INVENTION_TECHNICAL_FIELD", "Please provide a brief description of the technical field of the invention? (max 100 words)"))
    adm.addInformationQuestion("REL_PRIOR_ART",             _q(questions, "INFO_REL_PRIOR_ART",             "Please briefly describe the relevant prior art (max 100 words)"))
    
    #F13
    adm.addQuestionInstantiator(
    _q(questions, "Q1", "[Q1] Is there a candidate/s which you have been given access to for the relevant prior art which has a similar purpose to the invention?"),
    {
        "They have the same or a very similar purpose.": "SimilarPurpose",
        "They have a different purpose.": ""
    },None,
    "field_questions")

    #F14
    adm.addQuestionInstantiator(
    _q(questions, "Q2", "[Q2] Are there similar technical effects between the candidate/s for the relevant prior art, from the prior question, and the invention?"),
    {
        "It produces a similar technical effect.": "SimilarEffect",
        "It produces a different technical effect.": ""
    },None,
    "field_questions_2")

    #F15/F16
    adm.addQuestionInstantiator(
    _q(questions, "Q3", "[Q3] What is the relationship between the candidate/s for the relevant prior art and the invention\'s technical field?"),
    {
        "It is from the exact same technical field.": "SameField",
        "It is from a closely related or analogous technical field.": "SimilarField",
        "It is from an unrelated technical field.": ""
    },
    None,
    "field_questions_3")

    adm.addInformationQuestion("CGK", _q(questions, "INFO_CGK", "Please briefly describe the common general knowledge"))

    #F8
    adm.addNodes("Contested", question=_q(questions, "Q4", "[Q4] Is there a reason we might want to contest what constitutes the Common General Knowledge in this instance? Only respond yes if there is a specific reason to challenge this otherwise we can assume the validity of the Common General Knowledge."))
    
    #F9/F10/F11
    adm.addQuestionInstantiator(
        _q(questions, "Q5", "[Q5] As we are contesting the common general knowledge, we must now evaluate what primary sources of evidence could be provided or cited or assumed for the Common General Knowledge?"),
        {
            "A standard textbook": "Textbook",
            "A broad technical survey": "TechnicalSurvey",
            "A single publication in a very new or rapidly evolving field.":"PublicationNewField",
            "A single publication in an established field.": "SinglePublication",
            "No documentary evidence is provided.": '' ,
            "Other":''
        },None,
        question_order_name="field_questions_4",
        gating_node= 'Contested'
    )
    
    #F1
    adm.addNodes("SkilledIn", question=_q(questions, "Q6", "These next few questions are to help establish who the 'person skilled in the art' is. This is a hypothetical person. \n\n[Q6] Is the skilled person skilled in the relevant technical field of the prior art?"))
    #F2    
    adm.addNodes("Average", question=_q(questions, "Q7", "[Q7] Would the skilled person possess at least average knowledge and ability for that field?"))
    #F3
    adm.addNodes("Aware", question=_q(questions, "Q8", "[Q8] Is there reason to believe the skilled person is aware of the common general knowledge in the field?"))
    #F4
    adm.addNodes("Access", question=_q(questions, "Q9", "[Q9] Would the skilled person have reasonable access to all the documents comprising the state of the art i.e. there are no clear barriers to access?"))
 
    #F5/F6/F7
    adm.addQuestionInstantiator(
    _q(questions, "Q10", "[Q10] Which of the following, if any, characterise the the skilled person/s?"),
    {
        "An individual practitioner": "Individual",
        "A research team": "ResearchTeam",
        "A production or manufacturing team": "ProductionTeam",
        "Other": ''
    }, {
        "Individual": {"SkilledPerson": "Please describe the individual practitioner"},
        "ResearchTeam": {"SkilledPerson": "Please describe the research team"},
        "ProductionTeam": {"SkilledPerson": "Please describe the production or manufacturing team"}
    },
    question_order_name="skilled_person",
    )

    #F19
    adm.addQuestionInstantiator(
    _q(questions, "Q11", "[Q11] Do we have a candidate for a singular closest prior art document? (Note: we can combine with other prior art documents in a subsequent question, so you can choose 1 to be the closest if there are multiple documents)"),
    {
        "Yes": "SingleReference",
        "No": ''
    }, 
    {
        "SingleReference": {"CPA": "Please describe the candidate for the closest prior art"},
    },
    question_order_name="SingleReference"
    )
    
    #F20/F21
    adm.addQuestionInstantiator(
    _q(questions, "Q12", "[Q12] Does the candidate closest prior art document constitute a promising starting point for a development leading to the invention. Generally this corresponds to a similar use and the fulfilment of a minimal set of structural and functional modifications to arrive at the claimed invention, as assessed from the perspective of the skilled person. This is required for the document to be considered the closest prior art."),
    {
        "Yes": ["MinModifications","AssessedBy"],
        "No": ''
    }, None,
    question_order_name="cpa_min_mod")
    
    #F22
    adm.addNodes("CombinationAttempt", question=_q(questions, "Q13", "[Q13] Is there a reason to combine other documents with the closest prior art in order to attempt to demonstrate obviousness?"))
    
    #F17/F18
    adm.addQuestionInstantiator(
    _q(questions, "Q14", "[Q14] How are the other documents to be combined related to the closest prior art's technical field"),
    {
        "They are from the same technical field": "SameFieldCPA",
        "They are from a similar technical field": "SimilarFieldCPA",
        "They are from an unrelated field": ""
    }, None,
    question_order_name="combined_docs",
    gating_node='CombinationAttempt'
    )
    
    #F23
    adm.addGatedBLF("CombinationMotive", 'CombinationAttempt', 
                        _q(questions, "Q15", "[Q15] Would the skilled person have a clear and direct motive to combine these specific documents?"))

    adm.addGatedBLF("BasisToAssociate", 
                        'CombinationAttempt',
                        _q(questions, "Q16", "[Q16] Is there a reasonable basis for the skilled person to associate these specific documents with one another?"))
    
    #AF5
    adm.addNodes("RelevantPriorArt", ['SameField','SimilarField','SimilarPurpose','SimilarEffect'], ['the relevant prior art is from the same field','the relevant prior art is from a similar field','the relevant prior art has a similar purpose','the relevant prior art has a similar effect','a relevant prior art cannot be established'])
    #AF4
    adm.addNodes("DocumentaryEvidence", ['reject SinglePublication','Textbook','TechnicalSurvey','PublicationNewField'], ['a single publication is not documentary evidence','a textbook is the documentary evidence','a technical survey is the documentary evidence','a publication in a new or emerging field is the documentary evidence', 'no documentary evidence for common knowledge provided'])
    #AF3
    adm.addNodes("CommonKnowledge", ['DocumentaryEvidence','reject Contested','accept'], ['common knowledge evidenced', 'no common knowledge established', 'common knowledge not disputed'])
    #AF1
    adm.addNodes("Person", ['Individual','ResearchTeam','ProductionTeam'], ['the skilled practitioner is an individual','the skilled practitioner is a research team','the skilled practitioner is a production team','the skilled practitioner does not fall within a vaild category'])
    #AF2
    adm.addNodes("SkilledPerson", ['SkilledIn and Average and Aware and Access and Person'], ['there is a defined skilled person','there is not a skilled person'])
    #AF6
    adm.addNodes("ClosestPriorArt", ['RelevantPriorArt and SingleReference and MinModifications and AssessedBy'], ['the closest prior art has been established','the closest prior art cannot be identified'])
    #AF7
    adm.addNodes("CombinationDocuments", ['CombinationAttempt and SameFieldCPA and CombinationMotive and BasisToAssociate and ClosestPriorArt','CombinationAttempt and SimilarFieldCPA and CombinationMotive and BasisToAssociate and ClosestPriorArt'], ['the combination of documents relevant to the closest prior art come from the same field','the combination of documents relevant to the closest prior art come from a similar field','no combination of documents relevant to the closest prior art'])
    #AF8
    adm.addNodes("ClosestPriorArtDocuments", ['CombinationDocuments and CommonKnowledge','ClosestPriorArt and CommonKnowledge'], ['the closest prior art consists of a combination of documents in combination with common general knowledge','the closest prior art consists of a document of a single reference in combination with common general knowledge','no set of closest prior documents could be determined'])
    
    #NEW AF!!!!
    adm.addNodes("Valid",['SkilledPerson and ClosestPriorArtDocuments'],['the conceptual components of the invention have been established, we may now assess inventive step','the conceptual components of the invention could not be established, the process will now terminate'],root=True)
    
    # Set question order to ask information questions first
    adm.questionOrder = ["INVENTION_TITLE", "INVENTION_DESCRIPTION", "INVENTION_TECHNICAL_FIELD", "REL_PRIOR_ART", 
    "field_questions","field_questions_2","field_questions_3",'CGK','Contested','field_questions_4','SkilledIn',
    'Average','Aware','Access','skilled_person','SingleReference','cpa_min_mod',"CombinationAttempt",'combined_docs',
    'CombinationMotive','BasisToAssociate']
    
    return adm

#Sub-ADM 1 
def sub_adm_1(item_name, questions: dict | None = None):
    """Creates a sub-ADM.

    Args:
        item_name: The name of the feature being evaluated.
        questions: Optional questions dict for prompt ablation.
    """
    sub_adm = ADM(item_name)
    n = item_name  # shorthand for format substitutions

    #blfs
    #F30 - Q17
    sub_adm.addQuestionInstantiator(
    _q(questions, "Q17", f"[Q17] Does the feature under consideration make a technical contribution? This means it must have a technical effect.\n\nFeature: {n}", feature_name=n),
    {
        "It produces an independent technical contribution.": "IndependentContribution",
        "It produces a contribution in combination with other technical features to the invention?": "CombinationContribution",
        "It does not produce a technical contribution.": ""
    },None,
    "tech_cont")
    
    #F33/F34/F35/F36 - Q19
    sub_adm.addQuestionInstantiator(
    _q(questions, "Q19", f"[Q19] What is the primary nature of the distinguishing feature under consideration?\n\nFeature: {n}", feature_name=n),
    {
        "A computer simulation": "ComputerSimulation",
        "The processing of numerical data": "NumericalData",
        "A mathematical method or algorithm": "MathematicalMethod",
        "Other excluded fields":"OtherExclusions",
        "None of the above":""
    },
    None,
    "nature_feat")

    #F32 - Q20
    sub_adm.addNodes("CircumventTechProblem", question=_q(questions, "Q20", f'[Q20] Is the feature under consideration a technical implementation of a non-technical method i.e. game rules or a business method, and does it circumvent the technical problem rather than addressing it in an inherently technical way?\n\nFeature: {n}', feature_name=n))

    #F41 - Q21
    sub_adm.addNodes("TechnicalAdaptation", question=_q(questions, "Q21", f'[Q21] Is the feature under consideration a specific technical adaptation which is specific for that implementation in that its design is motivated by technical considerations relating to the internal functioning of the computer system or network.\n\nFeature: {n}', feature_name=n))

    #bridge node to make things easier
    sub_adm.addNodes("NumOrComp",["NumericalData","ComputerSimulation"],["The feature involves numerical data","The feature involves a computer simulation","The feature does not involve a computer simulation or numerical data"])

    #F37 - Q22
    sub_adm.addGatedBLF("IntendedTechnicalUse","NumOrComp",
                            _q(questions, "Q22", f'[Q22] Is there an intended use of the data resulting from the feature under consideration?\n\nFeature: {n}', feature_name=n))
    #F38 - Q23
    sub_adm.addGatedBLF("TechUseSpecified","IntendedTechnicalUse",
                            _q(questions, "Q23", f'[Q23] Is there a potential technical effect of the data either explicitly or implicitly specified in the claim?\n\nFeature: {n}', feature_name=n))

    #F39 - Q24
    sub_adm.addGatedBLF("SpecificPurpose","MathematicalMethod",
                            _q(questions, "Q24", f'[Q24] Does the technical contribution of the feature under consideration have a specific technical purpose i.e. produces a technical effect serving a technical purpose. Not merely a `generic\' purpose i.e. "controlling a technical system".\n\nFeature: {n}', feature_name=n))

    #F40 - Q25
    sub_adm.addGatedBLF("FunctionallyLimited","MathematicalMethod",
                    _q(questions, "Q25", f'[Q25] Is the claim functionally limited to the technical purpose stated either explicitly or implicitly?\n\nFeature: {n}', feature_name=n))

    #F56 - Q26
    sub_adm.addNodes("UnexpectedEffect", question=_q(questions, "Q26", f'[Q26] Is the technical effect of the feature under consideration unexpected or surprising?\n\nFeature: {n}', feature_name=n))

    #F57 - Q27
    sub_adm.addGatedBLF("PreciseTerms","UnexpectedEffect",
                            _q(questions, "Q27", f'[Q27] Is this unexpected effect described in precise, measurable terms?\n\nFeature: {n}', feature_name=n))

    #F58 - Q28
    sub_adm.addGatedBLF("OneWayStreet",["UnexpectedEffect"],
                            _q(questions, "Q28", f'[Q28] Is the unexpected effect a result of a lack of alternatives creating a \'one-way street\' situation? i.e. for the skilled person to achieve the technical effect in question from the closest prior art, they would not have to choose from a range of possibilities, because there is only one-way to do x thing, and that would result in unexpected property y.\n\nFeature: {n}', feature_name=n))

    #F42,F43
    sub_adm.addQuestionInstantiator(
    _q(questions, "Q29", f"[Q29] Are the technical effects of the feature under consideration credible and/or reproducible?\n\nFeature: {n}", feature_name=n),
    {
        "Credible": ["Credible","NonReproducible"],
        "Reproducible": "",
        "Both": ["Credible","Reproducible"],
        "Neither": "NonReproducible"
    },
    None,
    "cred_repro_questions")

    #F44 - Q30
    sub_adm.addGatedBLF("ClaimContainsEffect","NonReproducible",
                            _q(questions, "Q30", f'[Q30] Do the claims contain the non-reproducible effect from the feature under consideration i.e. if the claim says the invention achieve effect E, and this is not reproducible.\n\nFeature: {n}', feature_name=n))

    sub_adm.addGatedBLF("SufficiencyOfDisclosureRaised","ClaimContainsEffect",
                            _q(questions, "Q31", f'[Q31] Is there an issue with sufficiency of disclosure regarding the feature under consideration i.e. an issue arises where there is not a \"A detailed description of at least one way of carrying out the invention must be given.\"?\n\nFeature: {n}', feature_name=n))

    #abstract factors
    sub_adm.addNodes("AppliedInField",["SpecificPurpose and FunctionallyLimited"],["the technical contribution is applied in the field","the technical contribution is not applied in the field"])
    sub_adm.addNodes("MathematicalContribution",["MathematicalMethod and AppliedInField","MathematicalMethod and TechnicalAdaptation"],["the technical contribution is a mathematical contribution applied in the field","the technical contribution is a mathematical contribution with a specific technical adaptation","the technical contribution is not a mathematical contribution"])
    sub_adm.addNodes("ComputationalContribution",["ComputerSimulation and TechnicalAdaptation","ComputerSimulation and IntendedTechnicalUse","NumericalData and IntendedTechnicalUse","NumericalData and TechUseSpecified"],["the technical contribution is a computational contribution with a specific technical adaptation","the technical contribution is a computational contribution with an intended technical use","the technical contribution is a numerical method with an intended technical use","the technical contribution is a numerical method with a specified technical use","there is no computational or numerical technical contribution"])
    #UPDATED
    sub_adm.addNodes("ExcludedField",["NumOrComp","MathematicalMethod","OtherExclusions"],["Computer simulations are typically excluded from being inventive","Numerical data is typically excluded from being inventive","Mathematical methods are typically excluded from being inventive","The feature is part of another excluded field","The feature is not part of an excluded field"])
    sub_adm.addNodes("NormalTechnicalContribution",["reject CircumventTechProblem","reject ExcludedField","IndependentContribution","CombinationContribution"],["The feature is not a technical contribution as it circumvents a technical problem","The feature is not a normal technical contribution as it is part of an excluded field","The feature is an independent technical contribution","The feature is a technical contribution in combination with other features","the feature is not a technical contribution"])
    sub_adm.addNodes("FeatureTechnicalContribution",["NormalTechnicalContribution","ComputationalContribution","MathematicalContribution"],["there is a technical contribution","there is a technical computational or numerical contribution","there is a technical mathematical contribution","there is no technical contribution"])
    sub_adm.addNodes("BonusEffect",["FeatureTechnicalContribution and UnexpectedEffect and OneWayStreet"],["there is a bonus effect","there is no bonus effect"])
    sub_adm.addNodes("SufficiencyOfDisclosureIssue",["ClaimContainsEffect and NonReproducible and SufficiencyOfDisclosureRaised"],["there is no issue with sufficiency of disclosure regarding this feature","there is an issue of sufficiency of disclosure as the claim states an effect which is not reproducible","no sufficiency of disclosure issue raised"])
    sub_adm.addNodes("ImpreciseUnexpectedEffect",["reject PreciseTerms","UnexpectedEffect"],["the unexpected effect is clearly and precisely described","the unexpected effect is not clearly and precisely described","there is no unexpected effect"])
    
    #root node
    sub_adm.addNodes("FeatureReliableTechnicalEffect",["reject SufficiencyOfDisclosureIssue","reject BonusEffect","reject ImpreciseUnexpectedEffect", "reject NonReproducible", "FeatureTechnicalContribution and Credible"],["An issue with sufficiency of disclosure is present so cannot be a reliable technical contribution","The feature is a bonus effect which precludes us relying on this feature","The feature is an unexpected effect so cannot be a reliable technical contribution", "The feature is non-reproducible so cannot be a reliable technical contribution","The feature is a credible, reproducible and reliable technical contribution","The feature is not a reliable technical contribution due to a lack of credibility/reproducibility or a technical contribution"],root=True)
    
    #The fact the sub-adm is running means there are distinguishing features so to more easily resolve this we just auto add it to eval later
    sub_adm.case = ["DistinguishingFeatures"]
    
    sub_adm.questionOrder = ["tech_cont","nature_feat","CircumventTechProblem","TechnicalAdaptation","IntendedTechnicalUse",
                             "TechUseSpecified","SpecificPurpose","FunctionallyLimited","UnexpectedEffect",
                             "PreciseTerms","OneWayStreet","cred_repro_questions","ClaimContainsEffect",
                             "SufficiencyOfDisclosureRaised"]
    
    return sub_adm

#Sub-ADM 2
def sub_adm_2(item_name, questions: dict | None = None):
    """Create sub-ADM for evaluating objective technical problems.

    Args:
        item_name: The name of the objective technical problem being evaluated.
        questions: Optional questions dict for prompt ablation.
    """
    sub_adm = ADM(item_name)
    n = item_name  # shorthand
    
    #BLFs
    #F48
    sub_adm.addNodes("Encompassed", question=_q(questions, "Q34", f'[Q34] Would the skilled person, consider the technical effects identified in the candidate objective technical problem to be encompassed and embodied by the technical teaching of the patent application i.e. is the objective technical problem reflected in the original application?\n\nProblem name: {n}', feature_name=n))

    #F50
    sub_adm.addNodes("ScopeOfClaim", question=_q(questions, "Q36", f'[Q36] Are the technical effects currently identified, achieved across the claims, and are the claims limited in such a way that all inventions which could be encompassed by the claims (taken as a whole so both independent and dependent) would show these effects? The technical effects used for formulating the objective technical problem have to be derivable from the application as filed when considered in the light of the closest prior art and the general common knowledge. All embodiments of the invention which are encompassed by the claims provided must demonstrate these effects. This does not mean all claims must exhibit this effect, only the inventions covered by them must. If there is at least 1 claim (dependent or independent) in which the technical effect can be achieved then answer Yes.\n\nProblem name: {n}', feature_name=n))

    #F52 
    sub_adm.addNodes("Hindsight", question=_q(questions, "Q38", f'[Q38] Has the objective technical problem been formulated in such a way as to refer to matters of which the skilled person would only have become aware by knowledge of the solution claimed i.e. is hindsight necessary to arrive at the objective technical problem?\n\nProblem name: {n}', feature_name=n))

    #F53/F54
    sub_adm.addQuestionInstantiator(
    _q(questions, "Q39", f"[Q39] Do you believe the skilled person would have arrived, not merely could have arrived, at the proposed invention by adapting or modifying the closest prior art, in light of the common general knowledge, because the prior art would have provided a clear motivation to do so in the expectation of some improvement or advantage? Make clear why they would have been motivated if you answer yes.\n\nProblem name: {n}", feature_name=n),
    {
        "Would have adapted from the prior art": "WouldAdapt",
        "Would have modified from the prior art": "WouldModify",
        "Neither":""
    },
    None,
    "modify_adapt")
    
    #AF32
    sub_adm.addNodes("BasicFormulation", ['Encompassed and ScopeOfClaim'], 
                    ['We have a valid basic formulation of the objective technical problem', 'We do not have a valid basic formulation of the objective technical problem'])
    
    #AF31
    sub_adm.addNodes("WellFormed", ['reject Hindsight','BasicFormulation'], 
                    ['The written formulation has been formed with hindsight', "The written formulation has been formed without hindsight", 'There is no written objective technical problem which has been formed without hindsight'])

    #AF30
    sub_adm.addNodes("ConstrainedProblem", ['WellFormed and NonTechnicalContribution'], 
                    ['There are non-technical contributions constraining the objective technical problem', 'There are no non-technical contributions constraining the objective technical problem'])    

    #AF29            
    sub_adm.addNodes("ObjectiveTechnicalProblemFormulation", ['ConstrainedProblem','WellFormed'], 
                    ['There is a valid objective technical problem formulation constrained by non-technical contributions', 'There is a valid objective technical problem formulation', 'There is no valid objective technical problem formulation'])     
    

    sub_adm.addNodes("WouldHaveArrived", ['WouldModify and  ObjectiveTechnicalProblemFormulation', 'WouldAdapt and ObjectiveTechnicalProblemFormulation'],
                    ['The skilled person would have arrived at the proposed invention by modifying the closest prior art', 'The skilled person would have arrived at the proposed invention by adapting the closest prior art','There is no reason to believe the skilled person would have arrived at the proposed invention'])
    
    #ROOT ISSUE 
    sub_adm.addNodes("ObjectiveProblemSolved", ['reject WouldHaveArrived', 'ObjectiveTechnicalProblemFormulation'],
                    ['The objective technical problem has been solved in an obvious way', 'There is evidence to show that the objective technical problem has been solved in a non-obvious way','The objective technical problem is not well-formed'],root=True)
    
    sub_adm.questionOrder = ["Encompassed","ScopeOfClaim","Hindsight","modify_adapt"]
    return sub_adm

def adm_main(sub_adm_1_flag=True, sub_adm_2_flag=True, questions: dict | None = None):
    
    """ 
    This ADM performs the main inventive step assessment.

    Args:
        sub_adm_1_flag: Include sub-ADM 1 (feature technical character).
        sub_adm_2_flag: Include sub-ADM 2 (objective technical problem).
        questions: Optional questions dict for prompt ablation.

    Returns:
        ADM instance.
    """
    adm = ADM("Inventive Step: Main")
    
    if sub_adm_1_flag:
        #Sub-ADM 1 instantiation - creates a list of items to instantiate sub-adms for
        def collect_features(adm):
            """Function to collect prior art items from user input"""
            
            differences = ("[Q] What differences between the invention and the closest prior art can be determined? List the features in the invention which are different (maximum of 5 features as a comma-separated list): ")
            #b = adm.resolveQuestionTemplate("[Q] What features does the invention have (combine into these into a max of 5, if the feature is the same as one in the closest prior art then phrase it the same way)?\nInvention title: {INVENTION_TITLE}\n\n(comma-separated list): ")
        
            available_items = input(differences).strip()
            #needed_items = input(b).strip()
            
            available_list = [item.strip() for item in available_items.split(',') if item.strip()]
            #needed_list = [item.strip() for item in needed_items.split(',') if item.strip()]
            
            counter = 0
            
            while len(available_list) > 5:
                available_items = input("[Q] Too many features listed, please condense them into 5. Ensure you don't use any sub-lists i.e. feature X has 1,2,3 as commas are interpreted as individual items!").strip()
                available_list = [item.strip() for item in available_items.split(',') if item.strip()]
                counter += 1
                if counter > 3:
                    return available_list
            
            #missing_items = [item for item in needed_list if item not in available_list]
            
            return available_list #missing_items

        #F28
        adm.addSubADMNode("ReliableTechnicalEffect", sub_adm=lambda name: sub_adm_1(name, questions), function=collect_features, rejection_condition=False)

        #F25
        adm.addEvaluationNode("DistinguishingFeatures", "ReliableTechnicalEffect", "DistinguishingFeatures", ['there are distinguishing features','there are no distinguishing features'])

        #F26
        adm.addEvaluationNode("NonTechnicalContribution", "ReliableTechnicalEffect", "FeatureTechnicalContribution", ['there is a non-technical contribution','there is no non-technical contribution'], rejection_condition=True)

        #F27
        adm.addEvaluationNode("TechnicalContribution", "ReliableTechnicalEffect", "FeatureTechnicalContribution", ['the features contain a technical contribution','The features do not contain a technical contribution'])
        
        #F29
        adm.addEvaluationNode("SufficiencyOfDisclosure", "ReliableTechnicalEffect", "SufficiencyOfDisclosureIssue", ['there is an issue with sufficiency of disclosure','there is no issue with sufficiency of disclosure'])

        #F62
        adm.addEvaluationNode("UnexpectedEffect", "ReliableTechnicalEffect", "UnexpectedEffect", ['there is an unexpected effect within the invention','there is not an unexpected effect within the invention'])
    
    else:
        adm.addNodes("DistinguishingFeatures", question=_q(questions, "Q100", "[Q100] Are there features which differ between the invention and the closest prior art?"))
       
        adm.addQuestionInstantiator(
        _q(questions, "Q101", "[Q101] Does at least one of the features of the invention have a technical contribution, and is this contribution credible and reproducible? This means it must have a technical effect."),
        {
            "Features only have a technical contribution": "TechnicalContribution",
            "Features have both technical and non-technical contributions": ["TechnicalContribution","NonTechnicalContribution"],
            "Features only have non-technical contributions": "NonTechnicalContribution",
            "None of the above": ""
        },
        None,
        "technical_contribution")
        
        adm.addNodes("UnexpectedEffect", question=_q(questions, "Q102", "[Q102] Is the technical effect of any of the features unexpected or surprising?"))

        adm.addGatedBLF("PreciseTerms","UnexpectedEffect",
                                _q(questions, "Q103", "[Q103] Is this unexpected effect described in precise, measurable terms?"))

        adm.addGatedBLF("OneWayStreet",["UnexpectedEffect"],
                                _q(questions, "Q104", "[Q104] Is the unexpected effect a result of a lack of alternatives creating a 'one-way street' situation? i.e. for the skilled person to achieve the technical effect in question from the closest prior art, they would not have to choose from a range of possibilities, because there is only one-way to do x thing, and that would result in unexpected property y."))
        
        adm.addQuestionInstantiator(
        _q(questions, "Q105", "[Q105] Are the technical effects of the features credible and/or reproducible?"),
        {
            "Credible": ["Credible","NonReproducible"],
            "Reproducible": "",
            "Both": ["Credible","Reproducible"],
            "Neither": "NonReproducible"
        },
        None,
        "cred_questions")

        adm.addGatedBLF("ClaimContainsEffect","NonReproducible",
                                _q(questions, "Q106", "[Q106] Do the claims contain non-reproducible effects from the features i.e. if the claim says the invention achieve effect E, and this is not reproducible."))

        adm.addGatedBLF("SufficiencyOfDisclosureRaised","ClaimContainsEffect",
                                _q(questions, "Q107", "[Q107] Is there an issue with sufficiency of disclosure i.e. an issue arises where there is not a \"A detailed description of at least one way of carrying out the invention must be given.\"?"))
      
        #Abstract Factors
        adm.addNodes("BonusEffect",["TechnicalContribution and UnexpectedEffect and OneWayStreet"],["there is a bonus effect","there is no bonus effect"])
        adm.addNodes("ImpreciseUnexpectedEffect",["reject PreciseTerms","UnexpectedEffect"],["the unexpected effect is clearly and precisely described","the unexpected effect is not clearly and precisely described","there is no unexpected effect"])
        adm.addNodes("SufficiencyOfDisclosure",["ClaimContainsEffect and NonReproducible and SufficiencyOfDisclosureRaised"],["there is no issue with sufficiency of disclosure regarding this feature","there is an issue of sufficiency of disclosure as the claim states an effect which is not reproducible","no sufficiency of disclosure issue raised"])
        adm.addNodes("ReliableTechnicalEffect",["reject SufficiencyOfDisclosure","reject BonusEffect","reject ImpreciseUnexpectedEffect", "reject NonReproducible", "TechnicalContribution and Credible"],["An issue with sufficiency of disclosure is present so cannot be a reliable technical contribution","The feature is a bonus effect which precludes us relying on this feature","The feature is an unexpected effect so cannot be a reliable technical contribution", "The feature is non-reproducible so cannot be a reliable technical contribution","The feature is a credible, reproducible and reliable technical contribution","The feature is not a reliable technical contribution due to a lack of credibility/reproducibility or a technical contribution"])

    ################
    
    #F46
    adm.addQuestionInstantiator(
    _q(questions, "Q32", "[Q32] How do the invention's technical features create the technical effect? Note: selecting an aggregation of independent effects implies the existence of partial objective technical problems. Use this if you believe the features are completely functionally independent from another, otherwise select the synergy option."),
    {
        "As a synergistic combination (effect is greater than the sum of parts).": "Synergy",
        "As a simple aggregation of independent effects.": "",
    },
    None,
    "synergy_question",
    gating_node= "ReliableTechnicalEffect")    
        

    #F45
    adm.addGatedBLF("FunctionalInteraction","Synergy",
                        _q(questions, "Q33", "[Q33] Is the synergistic combination achieved through a functional interaction between the technical features?"))

    if sub_adm_2_flag:
        #Sub-ADM 2 instantiation - creates a list of items to instantiate sub-adms for
        def collect_obj(adm):
            """Function to collect objective technical problems from user input based on sub-ADM results"""
            
            #get current case
            current_case = adm.case

            try:
                #get sub-ADM results from ReliableTechnicalEffect
                sub_adm_results = adm.getFact("ReliableTechnicalEffect_results")
                 # Extract technical and non-technical contributions from sub-ADM results
                technical_contributions = []
                non_technical_contributions = []
                    
            except:
                #print("No sub-ADM results found. Cannot determine technical contributions.")
                sub_adm_results = []
                technical_contributions = None
                non_technical_contributions = None

            #get the distinguished features list from ReliableTechnicalEffect
            distinguished_features_list = []
            try:
                distinguished_features_list = adm.getFact("ReliableTechnicalEffect_items") or []

            except Exception as e:
                #print(f"Warning: Could not retrieve distinguished features list: {e}")
                distinguished_features_list = []
            
           
            try:
                for i, case in enumerate(sub_adm_results):
                    if isinstance(case, list):
                        # Check if FeatureTechnicalContribution is in this case (technical contribution)
                        if "FeatureTechnicalContribution" in case:
                            # Get the corresponding distinguished feature from the list
                            if i < len(distinguished_features_list):
                                feature_name = distinguished_features_list[i]
                                technical_contributions.append(f"Feature {i+1}: {feature_name}")
                            else:
                                technical_contributions.append(f"Feature {i+1}: DistinguishingFeatures")
                        
                        # Check if FeatureTechnicalContribution is not in this case (non-technical contribution)
                        if "FeatureTechnicalContribution" not in case:
                            # Get the corresponding distinguished feature from the list
                            if i < len(distinguished_features_list):
                                feature_name = distinguished_features_list[i]
                                non_technical_contributions.append(f"Feature {i+1}: {feature_name}")
                            else:
                                non_technical_contributions.append(f"Feature {i+1}: NormalTechnicalContribution")
            except:
                pass
            # Present the features to the user
            print("\n" + "="*60)
            print("OBJECTIVE TECHNICAL PROBLEM FEATURE CONTRIBUTIONS")
            print("="*60)
            print("Objective Technical Problem Definition: The Objective Technical Problem (OTP) establishes the technical problem to be solved by studying the application (or the patent), the closest prior art and the differences (also called \"the distinguishing features\" of the claimed invention) in terms of features (either structural or functional) between the claimed invention and the closest prior art, identifying the technical effect resulting from the distinguishing features and then formulating the technical problem.\n i.e. the technical problem means the aim and task of modifying or adapting the closest prior art to achieve the technical effects that the invention offers over the closest prior art.")
            print("The objective technical problem must be formulated in such a way that it does not contain pointers to the technical solution.")
            print("Ensure you consider the objective technical problem in a holistic perspective across all of the objective technical problems considered.")
            print("="*60)

            if technical_contributions:
                if len(technical_contributions) > 0:
                    print(f"\nTechnical Contributions:")
                    for contrib in technical_contributions:
                        print(f"  - {contrib}")
                else:
                    print(f"\nTechnical Contributions: None found")

            if non_technical_contributions:
                if len(non_technical_contributions) > 0:
                    print(f"\nNon-Technical Contributions:")
                    for contrib in non_technical_contributions:
                        print(f"  - {contrib}")
                else:
                    print(f"\nNon-Technical Contributions: None found")

            
            #Check conditions and collect problems
            objective_problems = []
            
            if "Combination" in current_case:
                logger.debug("\nCombination detected in case - creating 1 objective technical problem:")
                
                hindsight = False
                
                while True:
                    
                    problem_desc = input("[Q] Please provide a short description of the objective technical problem: ").strip()
                    
                    if problem_desc:
                        
                        objective_problems.append(problem_desc)
                        print(f"Added problem: {problem_desc}")
                        
                        if hindsight is True:
                            break
                        
                        #check for hindsight when formulating the objective technical problem
                        hindsight_check = input(f'[Q380] To ensure the objective technical problem has not been formulated in such a way as to refer to matters of which the skilled person would only have become aware by knowledge of the solution claimed we must check whether the objective technical problem you have formulated has been formulated in hindsight i.e. is hindsight necessary to arrive at the objective technical problem? For example, if the objective technical problem includes the solution then it should be reformulated without hindsight. Think carefully about this. If you answer yes you will be given an opportunity to reformulate the objective technical problem. \n\n Objective Problem: {problem_desc}\n\nAnswer \'yes\' or \'no\' only (y/n):')
                
                        if hindsight_check.lower() == 'y' or hindsight_check.lower() == 'yes':
                            print('[Q] Please reformulate the objective technical problem without hindsight, and based on the technical effects, not on the solution if possible. If you do not believe it is possible then proceed to enter the same problem again.')                            
                            hindsight = True
                            objective_problems = []
                        else:
                            break
                    
                    else:
                        print("Input cannot be blank. Please provide a valid description.")
                
            
            if "PartialProblems" in current_case:
                logger.debug("\nPartialProblems detected in case - creating multiple problems:")
                print("In this instance the objective technical problem should be regarded as a set of several partial problems which are independently solved by different sets of distinguishing features. This is because there is not a synergistic relationship between the distinguishing features. Enter your formulation of the partial problems one by one. Do not create a separate problem for every single feature. Group the features into the minimum number of problems possible (ideally 2, max 3). Also, ensure that each problem has a unique identifier at the beginning.")
                hindsight = False
                
                while True:
                    
                    objective_problems = []
                    problem_count = 0
                    
                    while True:
                        #enforce the problem count limit to ensure it proceeds
                        if problem_count >= 5:
                            break
                        problem_desc = input(f"[Q] Enter Partial Problem {problem_count + 1} description (leave the line BLANK to finish by giving your answer as an empty string): ").strip()
                        if problem_desc.strip() == '' or problem_desc.strip() == 'BLANK':
                            break
                        if problem_desc:
                            objective_problems.append(problem_desc)
                            problem_count += 1
                            print(f"Added problem {problem_count}: {problem_desc}")
                    
                    if hindsight is True:
                        break
                        
                    #check for hindsight when formulating the partial problems
                    hindsight_check = input(f'[Q380] Have any one of the partial problems been formulated in such a way as to refer to matters of which the skilled person would only have become aware by knowledge of the solution claimed i.e. is hindsight necessary to arrive at the partial problems? or example, if any of the partial problems include the solution then they should be reformulated without hindsight. Think carefully.\n\n Objective Problems: {objective_problems}\n\n Answer yes or no only (y/n):')
                    if hindsight_check.lower() == 'y' or hindsight_check.lower() == 'yes':
                        print('[Q] Please reformulate the partial problems without hindsight and based on the technical effects, not on the solution if possible. If you do not believe it is possible then proceed to enter the same problem again.')                            
                        hindsight = True
                    else:
                        break
                
                    
            # Store the problems as facts in the adm
            if objective_problems:
                adm.setFact("objective_technical_problems", objective_problems)
            else:
                print("\nNo objective technical problems created")
            
            return objective_problems

        adm.addSubADMNode("OTPSolved", sub_adm=lambda name: sub_adm_2(name, questions), function=collect_obj, rejection_condition=False, check_node=['NonTechnicalContribution'])

        #F47 
        adm.addEvaluationNode("ValidOTP", "OTPSolved", "ObjectiveTechnicalProblemFormulation", ['there is at least 1 valid objective technical problem','there is no valid objective technical problem'])
        
    else:
        
        adm.addInformationQuestion('OBJ_T_PROBLEM', question=_q(questions, "INFO_OBJ_T_PROBLEM", "Objective Technical Problem Definition: The Objective Technical Problem (OTP) establishes the technical problem to be solved by studying the application (or the patent), the closest prior art and the differences (also called \"the distinguishing features\" of the claimed invention) in terms of features (either structural or functional) between the claimed invention and the closest prior art, identifying the technical effect resulting from the distinguishing features and then formulating the technical problem.\n i.e. the technical problem means the aim and task of modifying or adapting the closest prior art to achieve the technical effects that the invention offers over the closest prior art. The objective technical problem must be formulated in such a way that it does not contain pointers to the technical solution. \n\n[Q] Following this please formulate the objective technical problem/s."))
        
        adm.addNodes("Encompassed", question=_q(questions, "Q200", '[Q200] Would the skilled person, consider the technical effects identified in the objective technical problem to be encompassed and embodied by the technical teaching of the patent application i.e. is the objective technical problem reflected in the original application?'))

        adm.addNodes("ScopeOfClaim", question=_q(questions, "Q201", '[Q201] Are the technical effects currently identified, achieved across the claims, and are the claims limited in such a way that all inventions which could be encompassed by the claims (taken as a whole so both independent and dependent) would show these effects? The technical effects used for formulating the objective technical problem have to be derivable from the application as filed when considered in the light of the closest prior art and the general common knowledge. All embodiments of the invention which are encompassed by the claims provided must demonstrate these effects. This does not mean all claims must exhibit this effect, only the inventions covered by them must. If there is at least 1 claim (dependent or independent) in which the technical effect can be achieved then answer Yes.'))

        adm.addNodes("Hindsight", question=_q(questions, "Q202", '[Q202] Has the objective technical problem been formulated in such a way as to refer to matters of which the skilled person would only have become aware by knowledge of the solution claimed i.e. is hindsight necessary to arrive at the objective technical problem?'))

        adm.addQuestionInstantiator(
        _q(questions, "Q203", "[Q203] Do you believe the skilled person would have arrived, not merely could have arrived, at the proposed invention by adapting or modifying the closest prior art, in light of the common general knowledge, because the prior art would have provided a clear motivation to do so in the expectation of some improvement or advantage? Make clear why they would have been motivated if you answer yes."),
        {
            "Would have adapted from the prior art": "WouldAdapt",
            "Would have modified from the prior art": "WouldModify",
            "Neither":""
        },
        None,
        "modify_adapt")
        
        adm.addNodes("BasicFormulation", ['Encompassed and ScopeOfClaim'], 
                        ['We have a valid basic formulation of the objective technical problem', 'We do not have a valid basic formulation of the objective technical problem'])
        adm.addNodes("WellFormed", ['reject Hindsight','BasicFormulation'], 
                        ['The written formulation has been formed with hindsight', "The written formulation has been formed without hindsight", 'There is no written objective technical problem which has been formed without hindsight'])
        adm.addNodes("ConstrainedProblem", ['WellFormed and NonTechnicalContribution'], 
                        ['There are non-technical contributions constraining the objective technical problem', 'There are no non-technical contributions constraining the objective technical problem'])    

        adm.addNodes("ValidOTP", ['ConstrainedProblem','WellFormed'], 
                        ['There is a valid objective technical problem formulation constrained by non-technical contributions', 'There is a valid objective technical problem formulation', 'There is no valid objective technical problem formulation'])     
        
        adm.addNodes("WouldHaveArrived", ['WouldModify and  ValidOTP', 'WouldAdapt and ValidOTP'],
                        ['The skilled person would have arrived at the proposed invention by modifying the closest prior art', 'The skilled person would have arrived at the proposed invention by adapting the closest prior art','There is no reason to believe the skilled person would have arrived at the proposed invention'])
        
        adm.addNodes("OTPSolved", ['reject WouldHaveArrived', 'ValidOTP'],
                    ['The objective technical problem has been solved in an obvious way', 'There is evidence to show that the objective technical problem has been solved in a non-obvious way','The objective technical problem is not well-formed'])
    
        #F99
        #adm.addNodes("AgreeOTP",question="[Q99] Based on a holistic perspective across all of the objective technical problems considered, do you believe as a whole that the objective technical problem/s would be obvious to a person skilled in the art in light of the closest prior art and common general knowledge? Do not simply copy the results from before but use your own judgement to arrive at this conclusion.")
    
        
    #F59
    adm.addNodes("DisadvantageousMod", question=_q(questions, "Q40", "[Q40] Does the invention involve a disadvantageous modification of the prior art?"))

    #F60
    adm.addGatedBLF("Foreseeable",'DisadvantageousMod',
                        _q(questions, "Q41", "[Q41] Was this disadvantageous modification of the prior art foreseeable to the skilled person? i.e. could the skilled person have clearly predicted these disadvantages."))

    #F61
    adm.addGatedBLF("UnexpectedAdvantage",'DisadvantageousMod',
                        _q(questions, "Q42", "[Q42] Was the disadvantageous modification compensated for by an unexpected technical advantage?"))

    #F63
    adm.addNodes("BioTech", question=_q(questions, "Q43", "[Q43] Is the subject matter of the invention biotech?"))

    #F64
    adm.addGatedBLF("Antibody",'BioTech',
                        _q(questions, "Q44", "[Q44] Does the subject matter concern antibodies?"))

    #F67
    adm.addGatedBLF("PredictableResults",'BioTech',
                        _q(questions, "Q45", "[Q45] Were the results obtained as part of the invention clearly predictable?"))

    #F68
    adm.addGatedBLF("ReasonableSuccess",'BioTech',
                        _q(questions, "Q46", "[Q46] Was there a 'reasonable' expectation of success in obtaining the aforementioned results?"))

    #F65
    adm.addGatedBLF("KnownTechnique",'Antibody',
                        _q(questions, "Q47", "[Q47] Were the antibodies arrived at exclusively by applying techniques already known in the prior art or that would be common general knowledge?"))

    #F66
    adm.addGatedBLF("OvercomeTechDifficulty",'Antibody',
                        _q(questions, "Q48", "[Q48] Does the application of the antibodies overcome technical difficulties in generating or manufacturing them?"))

    #F69
    adm.addNodes("GapFilled", question=_q(questions, "Q49", "[Q49] Does the invention merely fill an obvious gap in an incomplete prior art document and at least one of the posssible ways of \"filling the gap\" would naturally occur to the skilled person? For example: The invention relates to a building structure made from aluminium. A prior-art document discloses the same structure and says that it is of light-weight material but does not mention the use of aluminium."))

    #F70
    adm.addNodes("WellKnownEquivalent", question=_q(questions, "Q50", "[Q50] Does the invention differ from the prior art solely in regard to substituting one well-known equivalent for another? For example: The invention relates to a pump which differs from a known pump solely in that its motive power is provided by a hydraulic motor instead of an electric motor."))

    #F71
    adm.addNodes("KnownProperties", question=_q(questions, "Q51", "[Q51] Is the invention merely the new use of known properties of a well-known material i.e. A washing composition containing as detergent, a known compound having the known property of lowering the surface tension of water."))

    #F72
    adm.addNodes("AnalogousUse", question=_q(questions, "Q52", "[Q52] Does the invention just apply a known technique in a closely analogous situation? For example: Example: The invention consists in the application of a pulse control technique to the electric motor driving the auxiliary mechanisms of an industrial truck, such as a fork-lift truck, the use of this technique to control the electric propulsion motor of the truck being already known."))

    #F73
    adm.addNodes("KnownDevice", question=_q(questions, "Q53", "[Q53] Does the invention rely on known devices?"))
    
    #F75
    adm.addGatedBLF("ObviousCombination",'KnownDevice',
                        _q(questions, "Q54", "[Q54] Is the invention a simple juxtaposition of the known devices, with each performing their normal, expected function?"))

    #F74
    adm.addGatedBLF("AnalogousSubstitution",'KnownDevice',
                        _q(questions, "Q55", "[Q55] Does the invention rely within a known device, simply substituting in a recently developed material suitable for that use?"))
    
    #F76
    adm.addNodes("ChooseEqualAlternatives", question=_q(questions, "Q56", "[Q56] Does the invention result from a choice between equally likely alternatives?"))
    
    #F77
    adm.addNodes("NormalDesignProcedure", question=_q(questions, "Q57", "[Q57] Does the invention consist in choosing parameters from a limited range of possibilities arrived at through routine design procedures?"))

    #F78
    adm.addNodes("SimpleExtrapolation", question=_q(questions, "Q58", "[Q58] Is the invention a result of a simple, straightforward extrapolation from the known art?"))

    #F79
    adm.addNodes("ChemicalSelection", question=_q(questions, "Q59", "[Q59] Does the invention just consist in selecting a specific chemical compound or composition from a broad field?"))
    
    #AF9
    adm.addNodes("Combination",['ReliableTechnicalEffect and FunctionalInteraction and Synergy'],['There is a synergy between all the technical effects', 'There is no synergy between all the technical effects'])
    #AF10    
    adm.addNodes("PartialProblems",['reject Combination','ReliableTechnicalEffect'],['There are not an aggregate of technical effects', 'There are an aggregate of technical effects', ""])
    
    #NEW -
    adm.addNodes('Contribution',['TechnicalContribution and NonTechnicalContribution','TechnicalContribution'],['There are both technical and non-technical contribution/s', 'There are technical contribution/s','There are no technical contributions'])
    
    #AF11 - updated
    adm.addNodes("CandidateOTP",['Combination and Contribution','PartialProblems and Contribution'],['There is a single objective technical problem','There are multiple partial problems which form the objective technical problem','There are no objective technical problems'])    
    
    #AF12
    adm.addNodes('SecondaryIndicator',['PredictableDisadvantage','BioTechObvious','AntibodyObvious','KnownMeasures','ObviousCombination','ObviousSelection'],['there is a secondary indicator - the invention contains a predictable disadvantage','there is a secondary indicator - the invention concerns an obvious use of biotechnology','there is a secondary indicator - the invention concerns an obvious use of antibodies','there is a secondary indicator - the invention contains known measures and consequently is obvious','there is a secondary indicator - the invention contains an obvious combination and consequently is obvious','there is a secondary indicator - the invention contains an obvious selection and consequently is obvious','there is no secondary indicator'])

    #AF13
    adm.addNodes('PredictableDisadvantage',['reject UnexpectedAdvantage','DisadvantageousMod and Foreseeable'],['there is an unexpected advantage','there is a disadvantageous modification of the prior art and it is foreseeable to the skilled person','there is no predictable disadvantage'])

    #AF14
    adm.addNodes('BioTechObvious',['reject UnexpectedEffect','BioTech and PredictableResults','BioTech and ReasonableSuccess'],['there is not an obvious biotech invention','there is an obvious biotech invention and the results are predictable','there is an obvious biotech invention and there is a reasonable expectation of success','there is not an obvious biotech invention'])

    #AF15
    adm.addNodes('AntibodyObvious',['reject OvercomeTechDifficulty','SubjectMatterAntibody and KnownTechnique'],['there is not an obvious antibody invention','there is an obvious antibody invention and the antibodies are arrived at exclusively by applying techniques known in the art','there is not an obvious antibody invention'])

    #AF16
    adm.addNodes('SubjectMatterAntibody',['BioTech and Antibody'],['the subject matter concerns antibodies','the subject matter does not concern antibodies'])

    #AF17
    adm.addNodes('KnownMeasures',['GapFilled','WellKnownEquivalent','KnownUsage'],['there is a known measure - completing missing but obvious details in prior art','there is a known measure - use of a well-known equivalent','there is a known measure involving known properties, an analogous use or analogous substitution ','there is not a known measure'])

    #AF18
    adm.addNodes('KnownUsage',['KnownProperties','AnalogousUse','KnownDevice and AnalogousSubstitution'],['there is a known usage - use of known properties','there is a known usage - use of an analogous use','there is a known usage - use of a known device and an analogous substitution','there is not a known usage'])

    #AF19
    adm.addNodes('ObviousSelection',['ChooseEqualAlternatives','NormalDesignProcedure','SimpleExtrapolation','ChemicalSelection'],['there is an obvious selection - the invention results from a choice between equally likely alternatives','there is an obvious selection - the invention consists in choosing parameters from a limited range of possibilities arrived at through routine design procedures','there is an obvious selection - the invention is a result of a simple, straightforward extrapolation from the known art','there is an obvious selection - the invention just consists in selecting a specific chemical compound or composition from a broad field','there is not an obvious selection'])

    #ISSUES

    #NEW — OTP is well-formed (candidate exists and is validly formulated)
    adm.addNodes('ObjectiveTechnicalProblem',['CandidateOTP and ValidOTP'],
                 ['there is a well-defined objective technical problem',
                  'there is no well-defined objective technical problem'])

    #NEW — OTP is well-formed AND was solved non-obviously by the invention
    adm.addNodes('NonObviousOTP',['ObjectiveTechnicalProblem and OTPSolved'],
                 ['the objective technical problem is well-defined and was solved in a non-obvious way',
                  'there is no non-obvious solution to a well-defined objective technical problem'])

    #I3
    adm.addNodes('Novelty',['DistinguishingFeatures'],['The invention has novelty','The invention has no novelty'])

    #I2 — invention is novel AND the OTP was solved non-obviously
    adm.addNodes('InventiveCandidate',['Novelty and NonObviousOTP','NonObviousOTP'],
                 ['the invention is novel and the objective technical problem was solved in a non-obvious way',
                  'the invention either lacks novelty or the objective technical problem was not solved in a non-obvious way'])

    #I1 - ROOT NODE
    adm.addNodes('InvStep',['reject SecondaryIndicator', 'reject SufficiencyOfDisclosure', 'InventiveCandidate'],
                 ['there is no inventive step due to a secondary indicator of obviousness',
                  'there is no inventive step due to sufficiency of disclosure',
                  'there is an inventive step present',
                  'there is no inventive step present'],root=True)
    
    if sub_adm_1_flag and sub_adm_2_flag:  
        adm.questionOrder = ['ReliableTechnicalEffect','DistinguishingFeatures','NonTechnicalContribution','TechnicalContribution','SufficiencyOfDisclosure',"UnexpectedEffect",
        "synergy_question","FunctionalInteraction","OTPSolved","ValidOTP", "DisadvantageousMod","Foreseeable",
        "UnexpectedAdvantage","BioTech","Antibody","PredictableResults","ReasonableSuccess","KnownTechnique",
        "OvercomeTechDifficulty","GapFilled","WellKnownEquivalent","KnownProperties","AnalogousUse",
        "KnownDevice","ObviousCombination","AnalogousSubstitution","ChooseEqualAlternatives",
        "NormalDesignProcedure","SimpleExtrapolation","ChemicalSelection"]
            
    elif sub_adm_1_flag:
        adm.questionOrder = ['ReliableTechnicalEffect','DistinguishingFeatures','NonTechnicalContribution','TechnicalContribution','SufficiencyOfDisclosure',"UnexpectedEffect",
        "synergy_question","FunctionalInteraction",'OBJ_T_PROBLEM','Encompassed','ScopeOfClaim','Hindsight','modify_adapt', "DisadvantageousMod","Foreseeable",
        "UnexpectedAdvantage","BioTech","Antibody","PredictableResults","ReasonableSuccess","KnownTechnique",
        "OvercomeTechDifficulty","GapFilled","WellKnownEquivalent","KnownProperties","AnalogousUse",
        "KnownDevice","ObviousCombination","AnalogousSubstitution","ChooseEqualAlternatives",
        "NormalDesignProcedure","SimpleExtrapolation","ChemicalSelection"]
    
    elif sub_adm_2_flag:
        adm.questionOrder = ["DistinguishingFeatures","technical_contribution","UnexpectedEffect","PreciseTerms","OneWayStreet","cred_questions","ClaimContainsEffect","SufficiencyOfDisclosureRaised",
        "synergy_question","FunctionalInteraction","OTPSolved","ValidOTP", "DisadvantageousMod","Foreseeable",
        "UnexpectedAdvantage","BioTech","Antibody","PredictableResults","ReasonableSuccess","KnownTechnique",
        "OvercomeTechDifficulty","GapFilled","WellKnownEquivalent","KnownProperties","AnalogousUse",
        "KnownDevice","ObviousCombination","AnalogousSubstitution","ChooseEqualAlternatives",
        "NormalDesignProcedure","SimpleExtrapolation","ChemicalSelection"]
    
    else:
        adm.questionOrder = ["DistinguishingFeatures","technical_contribution","UnexpectedEffect","PreciseTerms","OneWayStreet","cred_questions","ClaimContainsEffect","SufficiencyOfDisclosureRaised",
        "synergy_question","FunctionalInteraction",'OBJ_T_PROBLEM','Encompassed','ScopeOfClaim','Hindsight','modify_adapt', "DisadvantageousMod","Foreseeable",
        "UnexpectedAdvantage","BioTech","Antibody","PredictableResults","ReasonableSuccess","KnownTechnique",
        "OvercomeTechDifficulty","GapFilled","WellKnownEquivalent","KnownProperties","AnalogousUse",
        "KnownDevice","ObviousCombination","AnalogousSubstitution","ChooseEqualAlternatives",
        "NormalDesignProcedure","SimpleExtrapolation","ChemicalSelection"]
    
    return adm 

question_mapping = {
    # ── adm_initial (Q1–Q16) ──────────────────────────────────────────────
    "SimilarPurpose":           1,
    "SimilarEffect":            2,
    "SameField":                3,
    "SimilarField":             3,
    "Contested":                4,
    "Textbook":                 5,
    "TechnicalSurvey":          5,
    "PublicationNewField":      5,
    "SinglePublication":        5,
    "SkilledIn":                6,
    "Average":                  7,
    "Aware":                    8,
    "Access":                   9,
    "Individual":               10,
    "ResearchTeam":             10,
    "ProductionTeam":           10,
    "SingleReference":          11,
    "MinModifications":         12,
    "AssessedBy":               12,
    "CombinationAttempt":       13,
    "SameFieldCPA":             14,
    "SimilarFieldCPA":          14,
    "CombinationMotive":        15,
    "BasisToAssociate":         16,

    # ── sub_adm_1 (Q17–Q31) — used when sub_adm_1_flag=True ──────────────
    "IndependentContribution":  17,
    "CombinationContribution":  17,
    "ComputerSimulation":       19, 
    "NumericalData":            19,
    "MathematicalMethod":       19,
    "OtherExclusions":          19,
    "CircumventTechProblem":    20,
    "TechnicalAdaptation":      21,
    "IntendedTechnicalUse":     22,
    "TechUseSpecified":         23,
    "SpecificPurpose":          24,
    "FunctionallyLimited":      25,
    "Credible":                 29,
    "Reproducible":             29,
    "NonReproducible":          29,
    "ClaimContainsEffect":      30,
    "SufficiencyOfDisclosureRaised": 31,

    # ── main adm — shared questions (Q32–Q33) ─────────────────────────────
    "Synergy":                  32,
    "FunctionalInteraction":    33,

    # ── sub_adm_2 (Q34–Q39) — used when sub_adm_2_flag=True ──────────────
    "Encompassed":              34,
    "ScopeOfClaim":             36,  
    "Hindsight":                38,   
    "WouldAdapt":               39,
    "WouldModify":              39,

    # ── main adm — secondary-indicator questions (Q40–Q59) ────────────────
    "DisadvantageousMod":       40,
    "Foreseeable":              41,
    "UnexpectedAdvantage":      42,
    "BioTech":                  43,
    "Antibody":                 44,
    "PredictableResults":       45,
    "ReasonableSuccess":        46,
    "KnownTechnique":           47,
    "OvercomeTechDifficulty":   48,
    "GapFilled":                49,
    "WellKnownEquivalent":      50,
    "KnownProperties":          51,
    "AnalogousUse":             52,
    "KnownDevice":              53,
    "ObviousCombination":       54,
    "AnalogousSubstitution":    55,
    "ChooseEqualAlternatives":  56,
    "NormalDesignProcedure":    57,
    "SimpleExtrapolation":      58,
    "ChemicalSelection":        59,

    # ── sub_adm_1 BLFs that also appear in sub_adm_1 questions ───────────
    "UnexpectedEffect":         26,
    "PreciseTerms":             27,
    "OneWayStreet":             28,

    # ── ablation: no-sub_adm_1 flat questions (Q100–Q107) ─────────────────
    "DistinguishingFeatures":   100,
    "technical_contribution":   101,  
    "TechnicalContribution":    101,
    "NonTechnicalContribution": 101,
    "cred_questions":           105, 

    # ── ablation: no-sub_adm_2 flat questions (Q200–Q203) ─────────────────
    "OBJ_T_PROBLEM":            200,  
    "modify_adapt":             203,   
}









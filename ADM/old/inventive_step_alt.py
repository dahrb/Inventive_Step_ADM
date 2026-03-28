"""
Inventive Step ADM 

Last Updated: 21.02.2025

Status: Updating

Test Coverage: 49%

Version History:
v_1.0: initial version
v_2.0: changes the workings from 1.0 to be cleaner, easier to visualise and to understand; logic changes made to ensure better functioning
v_3.0: more substantial changes and different variations created for more robust testing
v_4.0: AI Augmented prompts

"""

from ADM_Construction import ADM

import logging

logger = logging.getLogger(__name__)

def adm_initial():
    """ 
    This ADM performs the ...

    Returns:
        
    """
    
    adm = ADM("Inventive Step: Preconditions")
    
    # Add information questions before the logic questions
    adm.addInformationQuestion("INVENTION_TITLE", "Identify and state the title of the invention being evaluated.")
    adm.addInformationQuestion("INVENTION_DESCRIPTION", "Provide a brief description of the invention (max 100 words), summarizing the core technical mechanism and intended utility.")
    adm.addInformationQuestion("INVENTION_TECHNICAL_FIELD", "Identify the technical field of the invention and define the specific engineering or scientific niche it occupies.")
    adm.addInformationQuestion("REL_PRIOR_ART", "Briefly describe the relevant prior art documents, such as D1 and D2, summarizing their key teachings.")
    
    #F13
    adm.addQuestionInstantiator(
    "[Q1] Prior Art Objective: Does the prior art share a similar technical purpose or goal with the claimed invention?",
    {
        "They have the same or a very similar purpose.": "SimilarPurpose",
        "They have a different purpose.": ""
    },None,
    "field_questions")

    #F14
    adm.addQuestionInstantiator(
    "[Q2] Technical Outputs: Does the prior art produce technical effects or performance characteristics that are comparable to the invention?",
    {
        "It produces a similar technical effect.": "SimilarEffect",
        "It produces a different technical effect.": ""
    },None,
    "field_questions_2")

    #F15/F16
    adm.addQuestionInstantiator(
    "[Q3] Field Assessment: Does the prior art document belong to the same (or a closely related) technical field as the invention?",
    {
        "It is from the exact same technical field.": "SameField",
        "It is from a closely related or analogous technical field.": "SimilarField",
        "It is from an unrelated technical field.": ""
    },
    None,
    "field_questions_3")

    adm.addInformationQuestion("CGK", "Briefly describe the common general knowledge available to a practitioner at the effective filing date.")

    #F8
    adm.addNodes("Contested", question="[Q4] CGK Dispute: Is there a documented factual or legal conflict between the parties regarding what constitutes the 'Common General Knowledge'?")
    
    #F9/F10/F11
    adm.addQuestionInstantiator(
        "[Q5] CGK Evidence: Is the Common General Knowledge based on standard textbooks/general literature, or is it based on specific patent/scientific citations?",
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
    adm.addNodes("SkilledIn", question= "[Q6] PSA Identity: Has the Person Skilled in the Art (PSA) been defined as an expert operating within the relevant technical field?")
    #F2    
    adm.addNodes("Average", question="[Q7] PSA Profile: Is the hypothetical skilled person limited to average knowledge and routine ability, without exercising inventive skill?")
    #F3
    adm.addNodes("Aware",question="[Q8] PSA Awareness: Is the skilled person presumed to be aware of the common general knowledge relevant to their field?")
    #F4
    adm.addNodes("Access", question="[Q9] State of the Art Access: Would the skilled person have had reasonable access to the cited prior art documents at the filing date?")
 
    #F5/F6/F7
    adm.addQuestionInstantiator(
    "[Q10] PSA Composition: Should the hypothetical expert be characterized as a single practitioner, a research team, or a manufacturing unit?",
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
    "[Q11] CPA Identification: Has a reasonable candidate for the 'Closest Prior Art' (CPA) been identified from the available documents?",
    {
        "Yes": "SingleReference",
        "No": ''
    }, 
    {
        "SingleReference": {"CPA": "Describe the candidate for the closest prior art, summarizing its most relevant technical features in relation to the invention."},
    },
    question_order_name="SingleReference"
    )
    
    #F20/F21
    adm.addQuestionInstantiator(
    "[Q12] Suitable Starting Point: Is the selected Closest Prior Art a plausible and reasonable starting point for assessing obviousness (e.g., it addresses a similar problem)?",
    {
        "Yes": ["MinModifications","AssessedBy"],
        "No": ''
    }, None,
    question_order_name="cpa_min_mod")
    
    #F22
    adm.addNodes("CombinationAttempt", question= "[Q13] Motivation to Combine: Is there any suggestion or logical technical incentive in the state of the art that would prompt the skilled person to combine the CPA with other documents?")
    
    #F17/F18
    adm.addQuestionInstantiator(
    "[Q14] Secondary Art Field: Do the secondary documents used in the proposed combination belong to the same technical field as the CPA?",
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
                        "[Q15] Logical Incentive: Would the skilled person have had a clear technical motive to combine these specific teachings to solve the problem?")

    adm.addGatedBLF("BasisToAssociate", 
                        'CombinationAttempt',
                        "[Q16] Technical Basis: Is there a functional or structural link that would naturally prompt the skilled person to associate these separate disclosures?")
    
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
def sub_adm_1(item_name):
    """Creates a sub-ADM """
    sub_adm = ADM(item_name)

    #blfs
    #F30 - Q17
    sub_adm.addQuestionInstantiator(
    f"[Q17] Mixed-Claim Analysis: Do the distinguishing features contribute to the technical solution of a technical problem?\n\nFeature: {sub_adm.name}",
    {
        "It produces an independent technical contribution.": "IndependentContribution",
        "It produces a contribution in combination with other technical features to the invention?": "CombinationContribution",
        "It does not produce a technical contribution.": ""
    },None,
    "tech_cont")

    #F33/F34/F35/F36 - Q20
    sub_adm.addQuestionInstantiator(
    f"[Q19] Statutory Exclusion: Do the distinguishing features relate primarily to non-technical subject matter, such as mathematical models, computer programs, or business methods?\n\nFeature: {sub_adm.name}",
    {
        "A computer simulation": "ComputerSimulation",
        "The processing of numerical data": "NumericalData",
        "A mathematical method or algorithm": "MathematicalMethod",
        "Other excluded fields":"OtherExclusions",
        "None of the above":""
    },
    None,
    "nature_feat")

    #F32 - Q21
    sub_adm.addNodes("CircumventTechProblem",question=f'[Q20] Problem Circumvention: Is the technical problem bypassed using non-technical means instead of being solved technically?\n\nFeature: {sub_adm.name}')

    #F41 - Q22
    sub_adm.addNodes("TechnicalAdaptation",question=f'[Q21] Technical Adaptation: Does the implementation of the distinguishing features require specific technical adaptations beyond standard design?\n\nFeature: {sub_adm.name}')

    #bridge node to make things easier
    sub_adm.addNodes("NumOrComp",["NumericalData","ComputerSimulation"],["The feature involves numerical data","The feature involves a computer simulation","The feature does not involve a computer simulation or numerical data"])

    #F37 - Q23
    sub_adm.addGatedBLF("IntendedTechnicalUse","NumOrComp",
                            f'[Q22] Intended Effect: Is there a specific, identifiable technical effect that the feature was designed to achieve?\n\nFeature: {sub_adm.name}')
    #F38 - Q24
    sub_adm.addGatedBLF("TechUseSpecified","IntendedTechnicalUse",
                            f'[Q23] Specificity of Use: Does the invention specify a concrete technical application or use-case for these features?\n\nFeature: {sub_adm.name}')

    #F39 - Q26
    sub_adm.addGatedBLF("SpecificPurpose","MathematicalMethod",
                            f'[Q24] Technical Purpose: Is the application of these features directed toward a clear technical objective?\n\nFeature: {sub_adm.name}')

    #F40 - Q27
    sub_adm.addGatedBLF("FunctionallyLimited","MathematicalMethod",
                    f'[Q25] Functional Limitation: Are the features limited by the claim language to the performance of the stated technical purpose?\n\nFeature: {sub_adm.name}')

    #F56 - Q28
    sub_adm.addNodes("UnexpectedEffect",question=f'[Q26] Unexpected Effect: Does the invention produce a technical effect that would be considered unexpected or surprising to the skilled person?\n\nFeature: {sub_adm.name}')

    #F57 - Q29
    sub_adm.addGatedBLF("PreciseTerms","UnexpectedEffect",
                            f'[Q27] Objective Definition: Is the technical problem solved by the feature described in objective terms rather than vague aspirations?\n\nFeature: {sub_adm.name}')

    #F58 - Q30
    sub_adm.addGatedBLF("OneWayStreet",["UnexpectedEffect"],
                            f'[Q28] One-Way Street: Was the claimed solution the only realistic and viable path forward for the skilled person to achieve the goal?\n\nFeature: {sub_adm.name}')

    #F42,F43
    sub_adm.addQuestionInstantiator(
    f"[Q29] Credibility: Is the claimed technical effect credible and generally reproducible based on the technical disclosure?\n\nFeature: {sub_adm.name}",
    {
        "Credible": ["Credible","NonReproducible"],
        "Reproducible": "",
        "Both": ["Credible","Reproducible"],
        "Neither": "NonReproducible"
    },
    None,
    "cred_repro_questions")
   
    #F44 - Q32
    sub_adm.addGatedBLF("ClaimContainsEffect","NonReproducible",
                            f'[Q30] Claim Completeness: Does the claim include the essential technical features required to achieve the stated technical effect?\n\nFeature: {sub_adm.name}')

    sub_adm.addGatedBLF("SufficiencyOfDisclosureRaised","ClaimContainsEffect",
                            f'[Q31] Sufficiency of Disclosure: Is there a valid challenge regarding whether the description provides enough detail to enable the skilled person to perform the invention?\n\nFeature: {sub_adm.name}')

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
def sub_adm_2(item_name):
    """Create sub-ADM for evaluating objective technical problems"""
    sub_adm = ADM(item_name)
    
    #BLFs
    #F48
    sub_adm.addNodes("Encompassed",question=f'[Q34] Technical Basis Check: Does the application (as originally filed) provide a reasonable technical basis to support the objective technical problem?\n\nProblem name: {sub_adm.name}')

    #F50
    sub_adm.addNodes("ScopeOfClaim",question=f'[Q36] Claim Scope Alignment: Is the scope of the patent claim reasonably aligned with the actual technical contribution made to the art, rather than being overly broad?\n\nProblem name: {sub_adm.name}')

    #F52 
    sub_adm.addNodes("Hindsight",question=f'[Q38] Hindsight: Does the argument against inventive step rely on impermissible hindsight (i.e., using knowledge of the invention to reconstruct it)?\n\nProblem name: {sub_adm.name}')

    #F53/F54
    sub_adm.addQuestionInstantiator(
    f"[Q39] Could-Would Test: Would the skilled person have been motivated to modify the prior art to arrive at the invention in the hope of solving the problem (would), as opposed to merely being able to do so (could)?\n\nProblem name: {sub_adm.name}",
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

def adm_main(sub_adm_1_flag=True,sub_adm_2_flag=True):
    
    """ 
    This ADM performs the ...

    Returns:
        _type_: _description_
    """
    adm = ADM("Inventive Step: Main")
    
    if sub_adm_1_flag:
        #Sub-ADM 1 instantiation - creates a list of items to instantiate sub-adms for
        def collect_features(adm):
            """Function to collect prior art items from user input"""
            
            differences = ("[Q] Distinguishing Features: Does the claimed invention possess clear technical features that distinguish it from the Closest Prior Art? Identify and list each specific technical feature... (maximum of 5 features as a comma-separated list): ")
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
        adm.addSubADMNode("ReliableTechnicalEffect", sub_adm=sub_adm_1, function=collect_features, rejection_condition=False)

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
        adm.addNodes("DistinguishingFeatures", question="[Q100] Distinguishing Features: Does the claimed invention possess clear technical features that distinguish it from the Closest Prior Art?")
       
        adm.addQuestionInstantiator(
        f"[Q101] Technical Contribution: Do the identified distinguishing features contribute to the technical solution of a technical problem?",
        {
            "Features only have a technical contribution": "TechnicalContribution",
            "Features have both technical and non-technical contributions": ["TechnicalContribution","NonTechnicalContribution"],
            "Features only have non-technical contributions": "NonTechnicalContribution",
            "None of the above": ""
        },
        None,
        "technical_contribution")
        
        adm.addNodes("UnexpectedEffect",question= f"[Q102] Unexpected Effect: Is the resulting technical effect unexpected or surprising from the perspective of the skilled person?")

        adm.addGatedBLF("PreciseTerms","UnexpectedEffect",
                                f'[Q103] Objective Problem Definition: Is the technical problem formulated in objective terms rather than subjective or vague aspirations?')

        adm.addGatedBLF("OneWayStreet",["UnexpectedEffect"],
                                f'[Q104] One-Way Street: Does the claimed solution represent the only realistic path forward for the skilled person to achieve the stated goal?')
        
        adm.addQuestionInstantiator(
        f"[Q105] Credibility: Is the claimed technical effect credible and generally reproducible based on the disclosure provided?",
        {
            "Credible": ["Credible","NonReproducible"],
            "Reproducible": "",
            "Both": ["Credible","Reproducible"],
            "Neither": "NonReproducible"
        },
        None,
        "cred_questions")

        adm.addGatedBLF("ClaimContainsEffect","NonReproducible",
                                f'[Q106] Claim Completeness: Does the independent claim include the essential technical features necessary to solve the objective technical problem?')

        adm.addGatedBLF("SufficiencyOfDisclosureRaised","ClaimContainsEffect",
                                f'[Q107] Sufficiency of Disclosure: Is there a substantive challenge regarding whether the patent description provides enough detail to perform the invention?')
      
        #Abstract Factors
        adm.addNodes("BonusEffect",["TechnicalContribution and UnexpectedEffect and OneWayStreet"],["there is a bonus effect","there is no bonus effect"])
        adm.addNodes("ImpreciseUnexpectedEffect",["reject PreciseTerms","UnexpectedEffect"],["the unexpected effect is clearly and precisely described","the unexpected effect is not clearly and precisely described","there is no unexpected effect"])
        adm.addNodes("SufficiencyOfDisclosure",["ClaimContainsEffect and NonReproducible and SufficiencyOfDisclosureRaised"],["there is no issue with sufficiency of disclosure regarding this feature","there is an issue of sufficiency of disclosure as the claim states an effect which is not reproducible","no sufficiency of disclosure issue raised"])
        adm.addNodes("ReliableTechnicalEffect",["reject SufficiencyOfDisclosure","reject BonusEffect","reject ImpreciseUnexpectedEffect", "reject NonReproducible", "TechnicalContribution and Credible"],["An issue with sufficiency of disclosure is present so cannot be a reliable technical contribution","The feature is a bonus effect which precludes us relying on this feature","The feature is an unexpected effect so cannot be a reliable technical contribution", "The feature is non-reproducible so cannot be a reliable technical contribution","The feature is a credible, reproducible and reliable technical contribution","The feature is not a reliable technical contribution due to a lack of credibility/reproducibility or a technical contribution"])

    ################
        
    #F46
    adm.addQuestionInstantiator(
    "[Q32] Synergistic Interaction: Do the distinguishing features interact to produce a combined technical effect that is greater than the sum of their individual effects?",
    {
        "As a synergistic combination (effect is greater than the sum of parts).": "Synergy",
        "As a simple aggregation of independent effects.": "",
    },
    None,
    "synergy_question",
    gating_node= "ReliableTechnicalEffect")    
        

    #F45
    adm.addGatedBLF("FunctionalInteraction","Synergy",
                        "[Q33] Functional Interdependence: Do the features work together in a functional relationship to achieve the overall technical result?")

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
                    
                    problem_desc = input("[Q] Briefly describe the objective technical problem based on the technical effect of the distinguishing features over the Closest Prior Art. Avoid incorporating any features of the solution itself: ").strip()
                    
                    if problem_desc:
                        
                        objective_problems.append(problem_desc)
                        print(f"Added problem: {problem_desc}")
                        
                        if hindsight is True:
                            break
                        
                        #check for hindsight when formulating the objective technical problem
                        hindsight_check = input(f'[Q380] Hindsight Analysis: Review the formulated Objective Technical Problem. Does it incorporate information that the skilled person would only be aware of after seeing the claimed invention? (If \'y\', a neutral reformulation is required).\n\n Objective Problem: {problem_desc}\n\nAnswer \'yes\' or \'no\' only (y/n): ')
                
                        if hindsight_check.lower() == 'y' or hindsight_check.lower() == 'yes':
                            print('[Q] Please provide a neutral statement of the task to be solved. Focus strictly on the technical effects achieved and ensure the problem is defined without any ex post facto pointers to the technical solution.')                            
                            hindsight = True
                            objective_problems = []
                        else:
                            break
                    
                    else:
                        print("Input cannot be blank. Please provide a valid description.")
                
            
            if "PartialProblems" in current_case:
                logger.debug("\nPartialProblems detected in case - creating multiple problems:")
                print("In the absence of synergistic interaction, define the Objective Technical Problem as a set of independent 'Partial Problems.' Group features by technical effect and provide a neutral description for each, ensuring no solution-pointers are included.")
                hindsight = False
                
                while True:
                    
                    objective_problems = []
                    problem_count = 0
                    
                    while True:
                        #enforce the problem count limit to ensure it proceeds
                        if problem_count >= 5:
                            break
                        problem_desc = input(f"[Q] Provide a description for the next Partial Problem. Ensure it is formulated neutrally. Leave blank or enter 'BLANK' to conclude the sequence: ").strip()
                        if problem_desc.strip() == '' or problem_desc.strip() == 'BLANK':
                            break
                        if problem_desc:
                            objective_problems.append(problem_desc)
                            problem_count += 1
                            print(f"Added problem {problem_count}: {problem_desc}")
                    
                    if hindsight is True:
                        break
                        
                    #check for hindsight when formulating the partial problems
                    hindsight_check = input(f'[Q380] Hindsight Analysis (Partial Problems): Review the entire set of partial problems. Does any specific formulation rely on ex post facto knowledge of the claimed invention? Answer \'y\' if any problem requires reformulation to remove hindsight.\n\n Objective Problems: {objective_problems}\n\n Answer yes or no only (y/n): ')
                    if hindsight_check.lower() == 'y' or hindsight_check.lower() == 'yes':
                        print('[Q] Please provide a neutral statement of the task to be solved. Focus strictly on the technical effects achieved and ensure the problem is defined without any ex post facto pointers to the technical solution.')                            
                        hindsight = True
                    else:
                        break
                
                    
            # Store the problems as facts in the adm
            if objective_problems:
                adm.setFact("objective_technical_problems", objective_problems)
            else:
                print("\nNo objective technical problems created")
            
            return objective_problems

        adm.addSubADMNode("OTPNotObvious", sub_adm=sub_adm_2, function=collect_obj, rejection_condition=False, check_node=['NonTechnicalContribution'])

        #F47 
        adm.addEvaluationNode("ValidOTP", "OTPNotObvious", "ObjectiveTechnicalProblemFormulation", ['there is at least 1 valid objective technical problem','there is no valid objective technical problem'])
        
    else:
        
        adm.addInformationQuestion('OBJ_T_PROBLEM',question="Objective Technical Problem Definition: The Objective Technical Problem (OTP) establishes the technical problem to be solved by studying the application (or the patent), the closest prior art and the differences (also called \"the distinguishing features\" of the claimed invention) in terms of features (either structural or functional) between the claimed invention and the closest prior art, identifying the technical effect resulting from the distinguishing features and then formulating the technical problem.\n i.e. the technical problem means the aim and task of modifying or adapting the closest prior art to achieve the technical effects that the invention offers over the closest prior art. The objective technical problem must be formulated in such a way that it does not contain pointers to the technical solution.\n\n[Q] Briefly describe the objective technical problem (OTP) by identifying the technical effect achieved by the distinguishing features over the Closest Prior Art. Ensure the formulation contains no pointers to the claimed solution.")
        
        adm.addNodes("Encompassed",question=f'[Q200] Original Teaching Alignment: Does the original application provide a reasonable technical basis to support the objective technical problem?')

        adm.addNodes("ScopeOfClaim",question=f'[Q201] Claim Scope Alignment: Is the scope of the claim reasonably aligned with the actual technical contribution, rather than being overly broad?')

        adm.addNodes("Hindsight",question=f'[Q202] Hindsight: Does the argumentation against inventive step improperly rely on knowledge of the invention itself (impermissible hindsight)?')

        adm.addQuestionInstantiator(
        f"[Q203] Could-Would Test: Would the skilled person have been motivated to modify the art to arrive at the invention (would), rather than merely having the capability to do so (could)?",
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
        
        adm.addNodes("OTPNotObvious", ['reject WouldHaveArrived', 'ValidOTP'],
                    ['The objective technical problem has been solved in an obvious way', 'There is evidence to show that the objective technical problem has been solved in a non-obvious way','The objective technical problem is not well-formed'])
    
    #F59
    adm.addNodes("DisadvantageousMod",question="[Q40] Disadvantageous Modification: Does the invention involve a disadvantageous modification of the prior art (e.g., sacrificing one known benefit for another)?")

    #F60
    adm.addGatedBLF("Foreseeable",'DisadvantageousMod',
                        "[Q41] Foreseeable Disadvantage: Was this disadvantageous modification and its resulting drawbacks clearly foreseeable to the skilled person?")

    #F61
    adm.addGatedBLF("UnexpectedAdvantage",'DisadvantageousMod',
                        "[Q42] Unexpected Advantage: Was the disadvantageous modification adequately compensated for by an unexpected technical advantage?")

    #F63
    adm.addNodes("BioTech",question="[Q43] Biotech Domain: Does the subject matter of the invention relate specifically to biotechnology?")

    #F64
    adm.addGatedBLF("Antibody",'BioTech',
                        "[Q44] Antibody Domain: Does the subject matter of the invention specifically concern antibodies?")

    #F67
    adm.addGatedBLF("PredictableResults",'BioTech',
                        "[Q45] Predictable Results (Biotech): Were the results obtained in the biotech invention predictable using established scientific models?")

    #F68
    adm.addGatedBLF("ReasonableSuccess",'BioTech',
                        "[Q46] Expectation of Success (Biotech): Would the skilled person have had a 'reasonable expectation of success' before embarking on the biotech development?")

    #F65
    adm.addGatedBLF("KnownTechnique",'Antibody',
                        "[Q47] Known Antibody Techniques: Were the antibodies arrived at exclusively by applying techniques already known in the prior art?")

    #F66
    adm.addGatedBLF("OvercomeTechDifficulty",'Antibody',
                        "[Q48] Overcoming Technical Difficulty: Does the creation of the antibodies successfully overcome known technical difficulties in generating them?")

    #F69
    adm.addNodes("GapFilled", question= "[Q49] Obvious Gap Filling: Does the invention merely fill an obvious gap in an incomplete prior art document, where the solution would naturally occur to the skilled person?")

    #F70
    adm.addNodes("WellKnownEquivalent", question= "[Q50] Well-Known Equivalent: Does the invention differ from the prior art solely by substituting one well-known technical equivalent for another?")

    #F71
    adm.addNodes("KnownProperties",question="[Q51] Known Material Properties: Is the invention merely a new use relying solely on the inherent, previously known properties of a well-known material?")

    #F72
    adm.addNodes("AnalogousUse",question="[Q52] Analogous Use: Does the invention merely apply a known technique in a closely analogous technical situation?")

    #F73
    adm.addNodes("KnownDevice",question="[Q53] Known Devices: Does the invention rely entirely on the use of known devices?")
    
    #F75
    adm.addGatedBLF("ObviousCombination",'KnownDevice',
                        "[Q54] Routine Juxtaposition: Is the invention a simple juxtaposition of known devices, with each performing their normal function without synergy?")

    #F74
    adm.addGatedBLF("AnalogousSubstitution",'KnownDevice',
                        "[Q55] Analogous Substitution: Does the invention simply substitute a standard or suitable material into a known device?")
    
    #F76
    adm.addNodes("ChooseEqualAlternatives",question="[Q56] Arbitrary Selection: Does the invention result merely from an arbitrary choice between equally suitable known alternatives?")
    
    #F77
    adm.addNodes("NormalDesignProcedure",question="[Q57] Routine Design Parameters: Does the invention consist of choosing parameters from a limited range arrived at through routine design procedures?")

    #F78
    adm.addNodes("SimpleExtrapolation", question="[Q58] Simple Extrapolation: Is the invention a predictable, straightforward extrapolation from the existing state of the art?")

    #F79
    adm.addNodes("ChemicalSelection",question="[Q59] Chemical Selection: Does the invention merely consist of selecting a specific chemical compound from a broadly defined known field?") 
    
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
 
    #NEW
    adm.addNodes('ObjectiveTechnicalProblem',['CandidateOTP and ValidOTP'],['there is a well-defined objective technical problem','there is no well-defined objective technical problem '])
    
    #I3
    adm.addNodes('Novelty',['DistinguishingFeatures'],['The invention has novelty','The invention has no novelty'])

    #I2
    adm.addNodes('Obvious',['reject OTPNotObvious','SecondaryIndicator'],
                 ['the invention is not obvious','the invention is obvious due to secondary indicators','the invention is not obvious'])

    #I1 - ROOT NODE 
    adm.addNodes('InvStep',['reject Obvious', 'reject SufficiencyOfDisclosure', 'Novelty and ObjectiveTechnicalProblem'],
                 [ 'there is no inventive step due to obviousness', 'there is no inventive step due to sufficiency of disclosure', 'there is an inventive step present', 'there is no inventive step present'],root=True)
    
    if sub_adm_1_flag and sub_adm_2_flag:  
        adm.questionOrder = ['ReliableTechnicalEffect','DistinguishingFeatures','NonTechnicalContribution','TechnicalContribution','SufficiencyOfDisclosure',"UnexpectedEffect",
        "synergy_question","FunctionalInteraction","OTPNotObvious","ValidOTP", "DisadvantageousMod","Foreseeable",
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
        "synergy_question","FunctionalInteraction","OTPNotObvious","ValidOTP", "DisadvantageousMod","Foreseeable",
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


#NEEDS UPDATING
question_mapping = {
    # --- Inventive Step: Preconditions (adm_initial) ---
    "SimilarPurpose": 1,
    "SimilarEffect": 2,
    "SameField": 3,
    "SimilarField": 3,
    "Contested": 4,
    "Textbook": 5,
    "TechnicalSurvey": 5,
    "PublicationNewField": 5,
    "SinglePublication": 5,
    "SkilledIn": 6,
    "Average": 7,
    "Aware": 8,
    "Access": 9,
    "Individual": 10,
    "ResearchTeam": 10,
    "ProductionTeam": 10,
    "SingleReference": 11,
    "MinModifications": 12,
    "AssessedBy": 12,
    "CombinationAttempt": 13,
    "SameFieldCPA": 14,
    "SimilarFieldCPA": 14,
    "CombinationMotive": 15,
    "BasisToAssociate": 16,

    # --- Sub-ADM 1 (sub_adm_1) ---
    "IndependentContribution": 17,
    "CombinationContribution": 17,
    "ComputerSimulation": 19,
    "NumericalData": 19,
    "MathematicalMethod": 19,
    "OtherExclusions": 19,
    "CircumventTechProblem": 20,
    "TechnicalAdaptation": 21,
    "IntendedTechnicalUse": 22,
    "TechUseSpecified": 23,
    "SpecificPurpose": 24,
    "FunctionallyLimited": 25,
    "UnexpectedEffect": 26,
    "PreciseTerms": 27,
    "OneWayStreet": 28,
    "Credible": 29,
    "Reproducible": 29,
    "NonReproducible": 29,
    "ClaimContainsEffect": 30,
    "SufficiencyOfDisclosureRaised": 31,

    # --- Inventive Step: Main (adm_main - continued) ---
    "Synergy": 32,
    "FunctionalInteraction": 33,

    # --- Sub-ADM 2 (sub_adm_2) ---
    "Encompassed": 34,
    "Embodied": 35,
    "ScopeOfClaim": 36,
    "WrittenFormulation": 37,
    "Hindsight": 38,
    "WouldAdapt": 39,
    "WouldModify": 39,

    # --- Inventive Step: Main (adm_main - continued) ---
    "AgreeOTP": 99,
    "DisadvantageousMod": 40,
    "Foreseeable": 41,
    "UnexpectedAdvantage": 42,
    "BioTech": 43,
    "Antibody": 44,
    "PredictableResults": 45,
    "ReasonableSuccess": 46,
    "KnownTechnique": 47,
    "OvercomeTechDifficulty": 48,
    "GapFilled": 49,
    "WellKnownEquivalent": 50,
    "KnownProperties": 51,
    "AnalogousUse": 52,
    "KnownDevice": 53,
    "ObviousCombination": 54,
    "AnalogousSubstitution": 55,
    "ChooseEqualAlternatives": 56,
    "NormalDesignProcedure": 57,
    "SimpleExtrapolation": 58,
    "ChemicalSelection": 59
}
"""
Inventive Step ADM 2.0

- changes the workings from 1.0 to be cleaner, easier to visualise and to understand 
- logic changes made to ensure better functioning

Last Updated: 15.12.2025

Status: Testing

Test Coverage: 49%

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
    adm.addInformationQuestion("INVENTION_TITLE", "What is the title of your invention?")
    adm.addInformationQuestion("INVENTION_DESCRIPTION", "Please provide a brief description of your invention")
    adm.addInformationQuestion("INVENTION_TECHNICAL_FIELD", "Please provide a brief description of the technical field of the invention?")
    adm.addInformationQuestion("REL_PRIOR_ART", "Please briefly describe the relevant prior art")
    
    #F13
    adm.addQuestionInstantiator(
    "[Q1] Is there a candidate/s for the relevant prior art which have a similar purpose to the invention?",
    {
        "They have the same or a very similar purpose.": "SimilarPurpose",
        "They have a different purpose.": ""
    },None,
    "field_questions")

    #F14
    adm.addQuestionInstantiator(
    "[Q2] Are there similar technical effects between the candidate/s for the relevant prior art and the invention?",
    {
        "It produces a similar technical effect.": "SimilarEffect",
        "It produces a different technical effect.": ""
    },None,
    "field_questions_2")

    #F15/F16
    adm.addQuestionInstantiator(
    "[Q3] What is the relationship between the candidate/s for the relevant prior art and the invention\'s technical field?\n\nInvention Technical Field: {INVENTION_TECHNICAL_FIELD}",
    {
        "It is from the exact same technical field.": "SameField",
        "It is from a closely related or analogous technical field.": "SimilarField",
        "It is from an unrelated technical field.": ""
    },
    None,
    "field_questions_3")

    adm.addInformationQuestion("CGK", "Please briefly describe the common general knowledge")

    #F8
    adm.addNodes("Contested", question="[Q4] Is there an explicit reason to contest what constitutes the Common General Knowledge?\n\nCommon General Knowledge: {CGK}")
    
        #F9/F10/F11
    adm.addQuestionInstantiator(
        "[Q5] What is the primary source of evidence cited for the CGK?\n\nCommon General Knowledge: {CGK}",
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
    adm.addNodes("SkilledIn", question= "These next few questions are to help establish who the 'person skilled in the art' is. This is a hypothetical person. \n\n[Q6] Is the skilled person skilled in the relevant technical field of the prior art?\n\nRelevant Prior Art: {REL_PRIOR_ART}")

    #F2    
    adm.addNodes("Average", question="[Q7] Would the skilled person possess average knowledge and ability for that field?\n\nInvention Technical Field: {INVENTION_TECHNICAL_FIELD}")
    #F3
    adm.addNodes("Aware",question="[Q8] Is there reason to believe the skilled person is aware of the common general knowledge in the field?\n\nCommon General Knowledge: {CGK}")
    #F4
    adm.addNodes("Access", question="[Q9] Would the skilled person have reasonable access to all the documents comprising the state of the art i.e. there are no clear barriers to access?")
 
    #F5/F6/F7
    adm.addQuestionInstantiator(
    "[Q10] What is the nature of the skilled person?",
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
    "[Q11] Is the closest prior art document itself a single reference?",
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
    "[Q12] Does the candidate closest prior art document require minimal modifications to the invention as assessed from the perspective of the skilled person? This is required for the document to be considered the closest prior art.\n\nThe skilled person: {SkilledPerson}",
    {
        "Yes": ["MinModifications","AssessedBy"],
        "No": ''
    }, None,
    question_order_name="cpa_min_mod")
    
    #F22
    adm.addNodes("CombinationAttempt", question= "[Q13] Is there a reason to combine other documents with the closest prior art to attempt to demonstrate obviousness?\n\nClosest Prior: {CPA}\n\n")
    
    #F17/F18
    adm.addQuestionInstantiator(
    "[Q14] How are the other documents to be combined related to the closest prior art's technical field\n\nClosest Prior Art: {CPA}\n\n",
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
                        "[Q15] Would the skilled person have a clear and direct motive to combine these specific documents?\n\nThe skilled person: {SkilledPerson}\n\nClosest Prior: {CPA}\n\n")

    adm.addGatedBLF("BasisToAssociate", 
                        'CombinationAttempt',
                        "[Q16] Is there a reasonable basis for the skilled person to associate these specific documents with one another?\n\nThe skilled person: {SkilledPerson}\n\nClosest Prior: {CPA}\n\n")
    
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
    adm.addNodes("ClosestPriorArtDocuments", ['CombinationDocuments','ClosestPriorArt'], ['the closest prior art consists of a combination of documents','the closest prior art consists of a document of a single reference','no set of closest prior documents could be determined'])
    
    #NEW AF!!!!
    adm.addNodes("Valid",['CommonKnowledge and SkilledPerson and ClosestPriorArtDocuments'],['the conceptual components of the invention have been established, we may now assess inventive step','the conceptual components of the invention could not be established, the process will now terminate'],root=True)
    
    # Set question order to ask information questions first
    adm.questionOrder = ["INVENTION_TITLE", "INVENTION_DESCRIPTION", "INVENTION_TECHNICAL_FIELD", "REL_PRIOR_ART", "field_questions",
    "field_questions_2","field_questions_3",'CGK',"Contested",'field_questions_4','SkilledIn','Average','Aware','Access','skilled_person',
    'SingleReference','cpa_min_mod',"CombinationAttempt",'combined_docs','CombinationMotive','BasisToAssociate']
    
    return adm

#Sub-ADM 1 
def sub_adm_1(item_name):
    """Creates a sub-ADM """
    sub_adm = ADM(item_name)

    #blfs
    #F30 - Q17
    sub_adm.addNodes("IndependentContribution",question=f'[Q17] Does the feature under consideration make an independent technical contribution to the invention?\n\nFeature: {sub_adm.name}')

    #F31 - Q18
    sub_adm.addNodes("CombinationContribution",question=f'[Q18] Does the feature under consideration make a contribution in combination with other technical features to the invention?\n\nFeature: {sub_adm.name}')

    #F33/F34/F35/F36 - Q20
    sub_adm.addQuestionInstantiator(
    f"[Q19] What is the primary nature of the distinguishing feature under consideration?\n\nFeature: {sub_adm.name}",
    {
        "A computer simulation.": "ComputerSimulation",
        "The processing of numerical data.": "NumericalData",
        "A mathematical method or algorithm.": "MathematicalMethod",
        "Other excluded field":"OtherExclusions",
        "None of the above":""
    },
    None,
    "nature_feat")

    #F32 - Q21
    sub_adm.addNodes("CircumventTechProblem",question=f'[Q20] Is the feature under consideration a technical implementation of a non-technical method i.e. game rules or a business method, and does it circumvent the technical problem rather than addressing it in an inherently technical way?\n\nFeature: {sub_adm.name}')

    #F41 - Q22
    sub_adm.addNodes("TechnicalAdaptation",question=f'[Q21] Is the feature under consideration a specific technical adaptation which is specific for that implementation in that its design is motivated by technical considerations relating to the internal functioning of the computer system or network.\n\nFeature: {sub_adm.name}')

    #bridge node to make things easier
    sub_adm.addNodes("NumOrComp",["NumericalData","ComputerSimulation"],["The feature involves numerical data","The feature involves a computer simulation","The feature does not involve a computer simulation or numerical data"])

    #F37 - Q23
    sub_adm.addGatedBLF("IntendedTechnicalUse","NumOrComp",
                            f'[Q22] Is there an intended use of the data resulting from the feature under consideration?\n\nFeature: {sub_adm.name}')
    #F38 - Q24
    sub_adm.addGatedBLF("TechUseSpecified","IntendedTechnicalUse",
                            '[Q23] Is there a potential technical effect of the data either explicitly or implicitly specified in the claim?')

    #F39 - Q26
    sub_adm.addGatedBLF("SpecificPurpose","MathematicalMethod",
                            '[Q24] Does the technical contribution of the feature under consideration have a specific technical purpose i.e. produces a technical effect serving a technical purpose. Not merely a `generic\' purpose i.e. "controlling a technical system".')

    #F40 - Q27
    sub_adm.addGatedBLF("FunctionallyLimited","MathematicalMethod",
                    f'[Q25] Is the claim functionally limited to the technical purpose stated either explicitly or implicitly?\n\nFeature: {sub_adm.name}')

    #F56 - Q28
    sub_adm.addNodes("UnexpectedEffect",question=f'[Q26] Is the technical effect of the feature under consideration unexpected or surprising?\n\nFeature: {sub_adm.name}')

    #F57 - Q29
    sub_adm.addGatedBLF("PreciseTerms","UnexpectedEffect",
                            '[Q27] Is this unexpected effect described in precise, measurable terms?')

    #F58 - Q30
    sub_adm.addGatedBLF("OneWayStreet",["UnexpectedEffect"],
                            '[Q28] Is the unexpected effect a result of a lack of alternatives creating a \'one-way street\' situation? i.e. for the skilled person to achieve the technical effect in question from the closest prior art, they would not have to choose from a range of possibilities, because there is only one-way to do x thing, and that would result in unexpected property y.')

    #F42,F43
    sub_adm.addQuestionInstantiator(
    f"[Q29] Are the technical effects of the feature under consideration credible and/or reproducible?\n\nFeature: {sub_adm.name}",
    {
        "Credible": ["Credible","NonReproducible"],
        "Reproducible": "",
        "Both": ["Credible","Reproducible"],
        "Neither": "NonReproducible"
    },
    None,
    "cred_repro_questions")

   # removed
   # sub_adm.addNodes("NonReproducible",["reject Reproducible","accept"],["the technical effect is reproducible","the technical effect is not reproducible",""])
   
    #F44 - Q32
    sub_adm.addGatedBLF("ClaimContainsEffect","NonReproducible",
                            '[Q30] Do the claims contain the non-reproducible effect from the feature under consideration i.e. if the claim says the invention achieve effect E, and this is not reproducible.')

    sub_adm.addGatedBLF("SufficiencyOfDisclosureRaised","ClaimContainsEffect",
                            '[Q31] Is there an issue with sufficiency of disclosure regarding the feature under consideration i.e. an issue arises where there is not a \"A detailed description of at least one way of carrying out the invention must be given.\"?\n\nFeature: {sub_adm.name}')

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
    
    sub_adm.questionOrder = ["IndependentContribution","CombinationContribution","nature_feat","CircumventTechProblem","TechnicalAdaptation","IntendedTechnicalUse","TechUseSpecified","SpecificPurpose","FunctionallyLimited","UnexpectedEffect","PreciseTerms","OneWayStreet","cred_repro_questions","ClaimContainsEffect","SufficiencyOfDisclosureRaised"]
    
    return sub_adm

#Sub-ADM 2
def sub_adm_2(item_name):
    """Create sub-ADM for evaluating objective technical problems"""
    sub_adm = ADM(item_name)
    
    #BLFs
    #F48
    sub_adm.addNodes("Encompassed",question='[Q34] Would the skilled person, consider the technical effects identified in the candidate objective technical problem to be encompassed and embodied by the technical teaching of the patent application i.e. is the objective technical problem reflected in the original application?\n\nThe skilled person: {SkilledPerson}')

    #F49
    sub_adm.addNodes("Embodied",question='[Q35] Would the skilled person, consider the technical effects identified to be embodied by the same originally disclosed invention?\n\nThe skilled person: {SkilledPerson}')

    #F50
    sub_adm.addNodes("ScopeOfClaim",question='[Q36] Are the technical effects achieved across the whole scope of the claims, and are the claims limited in such a way that substantially all embodiments encompassed by the claim show these effects?')

    #F51
    sub_adm.addNodes("WrittenFormulation",question='[Q37] Can we construct a written formulation of the objective technical problem?')

    #F52
    sub_adm.addNodes("Hindsight",question='[Q38] Has the objective technical problem been formulated in such a way as to refer to matters of which the skilled person would only have become aware by knowledge of the solution claimed i.e. could we have only come up with the objetcive technical problem in hindsight?\n\nThe skilled person: {SkilledPerson}')

    #F53/F54
    sub_adm.addQuestionInstantiator(
    "[Q39] Do you believe the skilled person would have arrived at the proposed invention by adapting or modifying the closest prior art because the prior art would have provided motivation to do so in the expectation of some improvement or advantage?\n\nThe skilled person: {SkilledPerson}\n\nClosest Prior: {CPA}",
    {
        "Would have adapted from the prior art": "WouldAdapt",
        "Would have modified from the prior art": "WouldModify",
        "Neither":""
    },
    None,
    "modify_adapt")
    
    #AF32
    sub_adm.addNodes("BasicFormulation", ['Encompassed and Embodied and ScopeOfClaim'], 
                    ['We have a valid basic formulation of the objective technical problem', 'We do not have a valid basic formulation of the objective technical problem'])
    
    #AF31
    sub_adm.addNodes("WellFormed", ['reject Hindsight','WrittenFormulation and BasicFormulation'], 
                    ['The written formulation has been formed with hindsight', "The written formulation has been formed without hindsight", 'There is no written objective technical problem which has been formed without hindsight'])

    #AF30
    sub_adm.addNodes("ConstrainedProblem", ['WellFormed and NonTechnicalContribution'], 
                    ['There are non-technical contributions constraining the objective technical problem', 'There are no non-technical contributions constraining the objective technical problem'])    

    #AF29            
    sub_adm.addNodes("ObjectiveTechnicalProblemFormulation", ['ConstrainedProblem','WellFormed'], 
                    ['There is a valid objective technical problem formulation constrained by non-technical contributions', 'There is a valid objective technical problem formulation', 'There is no valid objective technical problem formulation'])     
    
    #ROOT ISSUE 
    sub_adm.addNodes("WouldHaveArrived", ['WouldModify and  ObjectiveTechnicalProblemFormulation', 'WouldAdapt and ObjectiveTechnicalProblemFormulation'],
                    ['The skilled person would have arrived at the proposed invention by modifying the closest prior art', 'The skilled person would have arrived at the proposed invention by adapting the closest prior art','no reason to believe the skilled person would have arrived at the proposed invention'],root=True)
    
    sub_adm.questionOrder = ["Encompassed","Embodied","ScopeOfClaim","WrittenFormulation","Hindsight","modify_adapt"]
    return sub_adm

def adm_main():
    
    """ 
    This ADM performs the ...

    Returns:
        _type_: _description_
    """
    
    adm = ADM("Inventive Step: Main")
    
    #Sub-ADM 1 instantiation - creates a list of items to instantiate sub-adms for
    def collect_features(adm):
        """Function to collect prior art items from user input"""
        
        a = adm.resolveQuestionTemplate("What features does the closest prior art have? (combine into these into a max of 5)\nClosest Prior Art: {CPA}\n\n(comma-separated list): ")
        b = adm.resolveQuestionTemplate("What features does the invention have (combine into these into a max of 5, if the feature is the same as one in the closest prior art then phrase it the same way)?\nInvention title: {INVENTION_TITLE}\n\n(comma-separated list): ")
       
        available_items = input(a).strip()
        needed_items = input(b).strip()
        
        available_list = [item.strip() for item in available_items.split(',') if item.strip()]
        needed_list = [item.strip() for item in needed_items.split(',') if item.strip()]
        
        missing_items = [item for item in needed_list if item not in available_list]
        
        return missing_items
    
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
    adm.addEvaluationNode("InventionUnexpectedEffect", "ReliableTechnicalEffect", "UnexpectedEffect", ['there is an unexpected effect within the invention','there is not an unexpected effect within the invention'])
    
    #F46
    adm.addQuestionInstantiator(
    "[Q32] How do the invention's technical features create the technical effect?",
    {
        "As a synergistic combination (effect is greater than the sum of parts).": "Synergy",
        "As a simple aggregation of independent effects.": "",
    },
    None,
    "synergy_question",
    gating_node= "ReliableTechnicalEffect")    

    #F45
    adm.addGatedBLF("FunctionalInteraction","Synergy",
                        "[Q33] Is the synergistic combination achieved through a functional interaction between fthe technical features?")

    #Sub-ADM 2 instantiation - creates a list of items to instantiate sub-adms for
    def collect_obj(adm):
        """Function to collect objective technical problems from user input based on sub-ADM results"""
        
        #get current case
        current_case = adm.case

        #get sub-ADM results from ReliableTechnicalEffect
        sub_adm_results = adm.getFact("ReliableTechnicalEffect_results")
        
        if not sub_adm_results:
            print("No sub-ADM results found. Cannot determine technical contributions.")
            return []

        #get the distinguished features list from ReliableTechnicalEffect
        distinguished_features_list = []
        try:
            distinguished_features_list = adm.getFact("ReliableTechnicalEffect_items") or []

        except Exception as e:
            print(f"Warning: Could not retrieve distinguished features list: {e}")
            distinguished_features_list = []
        
        # Extract technical and non-technical contributions from sub-ADM results
        technical_contributions = []
        non_technical_contributions = []
        
        for i, case in enumerate(sub_adm_results):
            if isinstance(case, list):
                # Check if FeatureTechnicalContribution is in this case (technical contribution)
                if "FeatureTechnicalContribution" in case:
                    # Get the corresponding distinguished feature from the list
                    if i < len(distinguished_features_list):
                        feature_name = distinguished_features_list[i]
                        technical_contributions.append(f"Case {i+1}: {feature_name}")
                    else:
                        technical_contributions.append(f"Case {i+1}: DistinguishingFeatures")
                
                # Check if FeatureTechnicalContribution is not in this case (non-technical contribution)
                if "FeatureTechnicalContribution" not in case:
                    # Get the corresponding distinguished feature from the list
                    if i < len(distinguished_features_list):
                        feature_name = distinguished_features_list[i]
                        non_technical_contributions.append(f"Case {i+1}: {feature_name}")
                    else:
                        non_technical_contributions.append(f"Case {i+1}: NormalTechnicalContribution")
        
        # Present the features to the user
        print("\n" + "="*60)
        print("OBJECTIVE TECHNICAL PROBLEM CONTRIBUTIONS")
        print("="*60)
        
        if technical_contributions:
            print(f"\nTechnical Contributions:")
            for contrib in technical_contributions:
                print(f"  - {contrib}")
        else:
            print(f"\nTechnical Contributions: None found")
            
        if non_technical_contributions:
            print(f"\nNon-Technical Contributions:")
            for contrib in non_technical_contributions:
                print(f"  - {contrib}")
        else:
            print(f"\nNon-Technical Contributions: None found")
        
        #Check conditions and collect problems
        objective_problems = []
        
        if "Combination" in current_case:
            print("\nCombination detected in case - creating 1 objective technical problem:")
            while True:
                problem_desc = input("Please provide a short description of the objective technical problem: ").strip()
                if problem_desc:
                    objective_problems.append(problem_desc)
                    print(f"Added problem: {problem_desc}")
                    break
                else:
                    print("Input cannot be blank. Please provide a valid description.")
        
        if "PartialProblems" in current_case:
            print("\nPartialProblems detected in case - creating multiple problems:")
            print("Enter problems one by one (max. 5). leave the line BLANK when finished by giving your answer as an empty string.")
            
            problem_count = 0
            while True:
                #enforce the problem count limit to ensure it proceeds
                if problem_count > 5:
                    break
                problem_desc = input(f"Enter Partial Problem {problem_count + 1} description OR leave the line BLANK to finish by giving your answer as an empty string): ").strip()
                if problem_desc.strip() == '' or problem_desc.strip() == 'BLANK':
                    break
                if problem_desc:
                    objective_problems.append(problem_desc)
                    problem_count += 1
                    print(f"Added problem {problem_count}: {problem_desc}")
        
        # Store the problems as facts in the adm
        if objective_problems:
            adm.setFact("objective_technical_problems", objective_problems)
        else:
            print("\nNo objective technical problems created")
        
        return objective_problems

    adm.addSubADMNode("OTPObvious", sub_adm=sub_adm_2, function=collect_obj, rejection_condition=True, check_node=['NonTechnicalContribution'])

    #F47 
    adm.addEvaluationNode("ValidOTP", "OTPObvious", "ObjectiveTechnicalProblemFormulation", ['there is a valid objective technical problem','there is not a valid objective technical problem'])

    #F59
    adm.addNodes("DisadvantageousMod",question="[Q40] Does the invention involve a disadvantageous modification of the prior art?\n\nRelevant Prior Art: {REL_PRIOR_ART}")

    #F60
    adm.addGatedBLF("Foreseeable",'DisadvantageousMod',
                        "[Q41] Was this disadvantageous modification of the prior art foreseeable to the skilled person?\n\nThe skilled person: {SkilledPerson}")

    #F61
    adm.addGatedBLF("UnexpectedAdvantage",'DisadvantageousMod',
                        "[Q42] Did the disadvantageous modification result in an unexpected technical advantage?")

    #F63
    adm.addNodes("BioTech",question="[Q43] Is the subject matter of the invention biotech?\n\nInvention description: {INVENTION_DESCRIPTION}")

    #F64
    adm.addGatedBLF("Antibody",'BioTech',
                        "[Q44] Does the subject matter concern antibodies?\n\nInvention description: {INVENTION_DESCRIPTION}")

    #F67
    adm.addGatedBLF("PredictableResults",'BioTech',
                        "[Q45] Were the results obtained as part of the invention clearly predictable?")

    #F68
    adm.addGatedBLF("ReasonableSuccess",'BioTech',
                        "[Q46] Was there a 'reasonable' expectation of success in obtaining the aforementioned results?")

    #F65
    adm.addGatedBLF("KnownTechnique",'Antibody',
                        "[Q47] Were the antibodies arrived at exclusively by applying techniques already known in the prior art or that would be common general knowledge?\n\nRelevant Prior Art: {REL_PRIOR_ART}\n\nCommon General Knowledge {CGK}")

    #F66
    adm.addGatedBLF("OvercomeTechDifficulty",'Antibody',
                        "[Q48] Does the application of the antibodies overcome technical difficulties in generating or manufacturing them?")

    #F69
    adm.addNodes("GapFilled", question= "[Q49] Does the invention merely fill an obvious gap in an incomplete prior art document which would naturally occur to the skilled person?\n\nRelevant Prior Art: {REL_PRIOR_ART}\n\nThe skilled person: {SkilledPerson}")

    #F70
    adm.addNodes("WellKnownEquivalent", question= "[Q50] Does the invention differ from the prior art in regard to substituting one well-known equivalent for another (e.g., a hydraulic for an electric motor)?\n\nRelevant Prior Art: {REL_PRIOR_ART}")

    #F71
    adm.addNodes("KnownProperties",question="[Q51] Is the invention merely the new use of known properties of a well-known material i.e. A washing composition containing as detergent, a known compound having the known property of lowering the surface tension of water.")

    #F72
    adm.addNodes("AnalogousUse",question="[Q52] Does the invention just apply a known technique in a closely analogous situation?")

    #F73
    adm.addNodes("KnownDevice",question="[Q53] Does the invention rely on known devices?")
    
    #F75
    adm.addGatedBLF("ObviousCombination",'KnownDevice',
                        "[Q54] Is the invention a simple juxtaposition of the known devices, with each performing their normal, expected function?")

    #F74
    adm.addGatedBLF("AnalogousSubstitution",'KnownDevice',
                        "[Q55] Does the invention rely within a known device, simply substituting in a recently developed material suitable for that use?")
    
    #F76
    adm.addNodes("ChooseEqualAlternatives",question="[Q56] Does the invention result from a choice between equally likely alternatives?")
    
    #F77
    adm.addNodes("NormalDesignProcedure",question="[Q57] Does the invention consist in choosing parameters from a limited range of possibilities arrived at through routine design procedures?")

    #F78
    adm.addNodes("SimpleExtrapolation", question="[Q58] Is the invention a result of a simple, straightforward extrapolation from the known art?")

    #F79
    adm.addNodes("ChemicalSelection",question="[Q59] Does the invention just consist in selecting a specific chemical compound or composition from a broad field?") 
    
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
    adm.addNodes('BioTechObvious',['reject InventionUnexpectedEffect','BioTech and PredictableResults','BioTech and ReasonableSuccess'],['there is not an obvious biotech invention','there is an obvious biotech invention and the results are predictable','there is an obvious biotech invention and there is a reasonable expectation of success','there is not an obvious biotech invention'])

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
    adm.addNodes('Obvious',['OTPObvious','SecondaryIndicator'],['the invention is obvious','the invention is obvious due to a secondary indicator','the invention is not obvious'])

    #I1 - ROOT NODE 
    adm.addNodes('InvStep',['reject SufficiencyOfDisclosure','reject Obvious','Novelty and ObjectiveTechnicalProblem'],['there is no inventive step due to sufficiency of disclosure','there is no inventive step due to obviousness','there is an inventive step present','there is no inventive step present'],root=True)

    # Set question order to ask information questions first
    adm.questionOrder = ['ReliableTechnicalEffect','DistinguishingFeatures','NonTechnicalContribution','TechnicalContribution','SufficiencyOfDisclosure',"InventionUnexpectedEffect",
    "synergy_question","FunctionalInteraction","OTPObvious","ValidOTP", "DisadvantageousMod","Foreseeable","UnexpectedAdvantage","BioTech","Antibody","PredictableResults","ReasonableSuccess","KnownTechnique","OvercomeTechDifficulty","GapFilled","WellKnownEquivalent","KnownProperties","AnalogousUse","KnownDevice","ObviousCombination","AnalogousSubstitution","ChooseEqualAlternatives","NormalDesignProcedure","SimpleExtrapolation","ChemicalSelection"
    ]
    
    return adm 

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
    "CombinationContribution": 18,
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









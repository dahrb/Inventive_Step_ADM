"""
Inventive Step ADM 2.0

- changes the workings from 1.0 to be cleaner, easier to visualise and to understand 
"""

from ADM_Construction import ADM

def adm_initial():
    """ 
    This ADM performs the ...

    Returns:
        _type_: _description_
    """
    
    adm = ADM("Inventive Step: Preconditions")
    
    # Add information questions before the logic questions
    adm.addInformationQuestion("INVENTION_TITLE", "\n\nWhat is the title of your invention?")
    adm.addInformationQuestion("INVENTION_DESCRIPTION", "\n\nPlease provide a brief description of your invention")
    adm.addInformationQuestion("INVENTION_TECHNICAL_FIELD", "\n\nWhat is the technical field of the invention?")
    adm.addInformationQuestion("REL_PRIOR_ART", "\n\nPlease briefly describe the relevant prior art")
    
    #F13
    adm.addQuestionInstantiator(
    "\n\nDo the candidate relevant prior art documents have a similar purpose to the invention?",
    {
        "They have the same or a very similar purpose.": "SimilarPurpose",
        "They have a different purpose.": ""
    },None,
    "field_questions")

    #F14
    adm.addQuestionInstantiator(
    "\n\nAre there similar technical effects between the candidate relevant prior art documents and the invention?",
    {
        "It produces a similar technical effect.": "SimilarEffect",
        "It produces a different technical effect.": ""
    },None,
    "field_questions_2")

    #F15/F16
    adm.addQuestionInstantiator(
    "\n\nWhat is the relationship between the candidate relevant prior art documents and the invention\'s technical field? \n\nInvention Technical Field: {INVENTION_TECHNICAL_FIELD} \n\n",
    {
        "It is from the exact same technical field.": "SameField",
        "It is from a closely related or analogous technical field.": "SimilarField",
        "It is from an unrelated technical field.": ""
    },
    None,
    "field_questions_3")

    adm.addInformationQuestion("CGK", "\n\nBriefly describe the common general knowledge")

    #F8
    adm.addNodes("Contested", question="\n\nIs the assertion of what constitutes Common General Knowledge being contested? \n\n Common General Knowledge: {CGK} \n\n")
    
        #F9/F10/F11
    adm.addQuestionInstantiator(
        "\n\nWhat is the primary source of evidence cited for the CGK? \n\n Common General Knowledge: {CGK} \n\n",
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
    adm.addNodes("SkilledIn", question= "\n\nIs the practitioner skilled in the relevant technical field of the prior art?\n\nRelevant Prior Art: {REL_PRIOR_ART}\n\n")

    #F2    
    adm.addNodes("Average", question="\nDoes the practitioner possess average knowledge and ability for that field?\n\n")

    #F3
    adm.addNodes("Aware",question="\n\nIs the practitioner presumed to be aware of the common general knowledge in the field?\n\nCommon General Knowledge: {CGK}\n\n")
    #F4
    adm.addNodes("Access", question="\n\nDoes the practitioner have access to all documents comprising the state of the art?\n\nCommon General Knowledge: {CGK}\n\n")
 
    #F5/F6/F7
    adm.addQuestionInstantiator(
    "\n\nWhat is the nature of this practitioner?",
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
    "\n\nIs the closest prior art document itself a single reference?",
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
    "\n\nDoes the closest prior art document require minimal modifications to the invention as assessed from the perspective of the skilled person? \n\n The skilled person: {SkilledPerson}",
    {
        "Yes": ["MinModifications","AssessedBy"],
        "No": ''
    }, None,
    question_order_name="cpa_min_mod")
    
    #F22
    adm.addNodes("CombinationAttempt", question= "\n\nIs there a reason to combine other documents with the CPA to attempt to demonstrate obviousness?\n\nClosest Prior: {CPA}\n\n")
    
    #F17/F18
    adm.addQuestionInstantiator(
    "\n\nHow are the other documents to be combined related to the CPA's technical field \n\n Closest Prior Art: {CPA}\n\n",
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
                        "\n\nWould the skilled person have a clear and direct motive to combine these specific documents?\n\n The skilled person: {SkilledPerson}\n\nClosest Prior: {CPA}\n\n")

    adm.addGatedBLF("BasisToAssociate", 
                        'CombinationAttempt',
                        "\n\nIs there a reasonable basis for the skilled person to associate these specific documents with one another?\n\n The skilled person: {SkilledPerson}\n\nClosest Prior: {CPA}\n\n")
    
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
    adm.addNodes("CombinationDocuments", ['CombinationAttempt and SameFieldCPA and CombinationMotive and BasisToAssociate','CombinationAttempt and SimilarFieldCPA and CombinationMotive and BasisToAssociate'], ['the combination of documents relevant to the closest prior art come from the same field','the combination of documents relevant to the closest prior art come from a similar field','no combination of documents relevant to the closest prior art'])
    #AF8
    adm.addNodes("ClosestPriorArtDocuments", ['CombinationDocuments','ClosestPriorArt'], ['the closest prior art consists of a combination of documents','the closest prior art consists of a document of a single reference','no set of closest prior documents could be determined'])
    
    #NEW AFS!!!!
    adm.addNodes("Valid",['CommonKnowledge and SkilledPerson and ClosestPriorArtDocuments'],['the conceptual components of the invention have been established, we may now assess inventive step','the conceptual components of the invention could not be established, the process will now terminate'])
    
    
    # Set question order to ask information questions first
    adm.questionOrder = ["INVENTION_TITLE", "INVENTION_DESCRIPTION", "INVENTION_TECHNICAL_FIELD", "REL_PRIOR_ART", "field_questions",
    "field_questions_2","field_questions_3",'CGK',"Contested",'field_questions_4','SkilledIn','Average','Aware','Access','skilled_person',
    'SingleReference','cpa_min_mod',"CombinationAttempt",'combined_docs','CombinationMotive','BasisToAssociate']
    
    return adm

def adm_main():
    pass
    











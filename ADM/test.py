import pandas as pd


RAW_DATA = pd.read_pickle("Data/train_data_Inv_Step.pkl")

case_name = 'T083412'

reasons = str(RAW_DATA.loc[RAW_DATA['Reference'] == case_name, 'Decision Reasons'].iloc[0])
decision = str(RAW_DATA.loc[RAW_DATA['Reference'] == case_name, 'Order'].iloc[0])

print(reasons)
print(decision)

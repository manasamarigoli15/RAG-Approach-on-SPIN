import pandas as pd # Helps Python talk to Excel files
import requests # Helps Python talk to websites
import time # Lets us pause between requests

# === 1. Load your Excel file ===
input_file = "Types_of_SPMs.xlsx"          #Existing file
output_file = "Types_of_SPMs_with_synonyms.xlsx" # New Excel created

df = pd.read_excel(input_file)

# Column name with PubChem IDs
ID_COL = "PubChem ID" 

# Clean PubChem IDs: remove spaces and weird characters
df[ID_COL] = df[ID_COL].astype(str).str.strip().str.replace("\u00a0", "", regex=False)

def clean_cid(value):
    """
    Make sure PubChem ID is clean:
    132472317.0  ->  "132472317"
    """
    try:
        return str(int(float(value)))   # handles 132472317.0 etc.
    except:
        return str(value).strip()


# === 2. Function to get synonyms from PubChem ===
def get_synonyms_from_pubchem(cid): # Function containing PubChem ID
    if cid is None or cid == "" or cid.lower() == "nan":
        return []

    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"

    try:
        r = requests.get(url, timeout=15) # Calls the website
        r.raise_for_status() # If the website said “Error”, this will raise an exception.
        data = r.json() # Interpret the answer as JSON

        #In that JSON reply, there is a path where synonyms live. We walk along that path and take the list of synonyms.
        synonyms = data["InformationList"]["Information"][0].get("Synonym", [])
        return synonyms
    except Exception as e:
        print(f"Error for CID {cid}: {e}")
        return []

# === 3. Loop through all rows and fetch synonyms ===
all_synonyms = []

for i, row in df.iterrows():
    raw_cid = row[ID_COL]
    cid = clean_cid(raw_cid)  # fix 132472317.0 -> "132472317"

    print(f"Fetching synonyms for CID {cid} ({i+1}/{len(df)})...")
    syns = get_synonyms_from_pubchem(cid)
    syns_joined = "; ".join(syns)
    all_synonyms.append(syns_joined)

    time.sleep(0.2)


# === 4. Save result ===
df["PubChem Synonyms"] = all_synonyms

df.to_excel(output_file, index=False)
print(f"Done! Saved with synonyms to: {output_file}")

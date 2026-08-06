#!/usr/bin/env python3
"""
Debug script to solve the latitude/longitude assignment issue.
"""

import pandas as pd

# Example data structures based on your description
# dam_location_SA: Contains dam names and their coordinates
# filtered_dam_df: Contains dam data with Clean_names column

# Let's recreate the issue and then solve it

# Sample data to demonstrate the problem
# Based on your actual output:
# filtered_dam_df has "willDam" like "Bronkhorstspruit Dam"
# and "Clean_names" like "Bronkhorstspruit" (just first word)
# dam_location_SA has "Name of dam" like "Bronkhorstspruit Dam"

dam_location_SA = pd.DataFrame({
    'Name of dam': ['Bronkhorstspruit Dam', 'Roodeplaat Dam', 'Buffelskloof Dam', 'Grootdraai Dam', 'Heyshope Dam'],
    'Decimal degree latitude': [-25.8065, -25.6483, -25.5731, -26.9833, -27.1667],
    'Decimal degree longitude': [28.7206, 28.3333, 30.0999, 29.2333, 30.0500]
})

filtered_dam_df = pd.DataFrame({
    'willDam': ['Bronkhorstspruit Dam', 'Roodeplaat Dam', 'Buffelskloof Dam', 'Grootdraai Dam', 'Heyshope Dam'],
    'River': ['Bronkhorstspruit River', 'Pienaars River', 'Waterval River', 'Vaal River', 'Assegaai River'],
    'FSC': [57.0, 41.2, 5.3, 349.8, 445.0],
    'This Week': [100.9, 100.6, 100.5, 99.9, 101.2],
    'Last Week': [101.4, 100.6, 100.6, 100.0, 101.4],
    'Last Year': [102.3, 100.5, 100.6, 100.9, 100.2]
})

# Create Clean_names column (as you did - taking first word)
clean_name_lst = []
for vals in filtered_dam_df["willDam"]:
    name_lst = vals.split(" ")
    clean_name_lst.append(name_lst[0])  # Takes "Bronkhorstspruit" from "Bronkhorstspruit Dam"

filtered_dam_df["Clean_names"] = clean_name_lst

print("Original filtered_dam_df:")
print(filtered_dam_df[['willDam', 'Clean_names']])
print("\nDam location data:")
print(dam_location_SA[['Name of dam', 'Decimal degree latitude', 'Decimal degree longitude']])

# YOUR ORIGINAL APPROACH (problematic):
print("\n=== ORIGINAL APPROACH (PROBLEMATIC) ===")
# This tries to match Clean_names (like "Bronkhorstspruit") with Name of dam (like "Bronkhorstspruit Dam")
# They don't match exactly, so active_dams will be empty!
active_dams = dam_location_SA[dam_location_SA["Name of dam"].isin(filtered_dam_df["Clean_names"])]
filtered_active_dams = filtered_dam_df[filtered_dam_df["Clean_names"].isin(active_dams["Name of dam"])]

print(f"Active dams count: {len(active_dams)}")
print(f"Filtered active dams count: {len(filtered_active_dams)}")

print("\nActive dams (with coords):")
print(active_dams[['Name of dam', 'Decimal degree latitude', 'Decimal degree longitude']])

print("\nFiltered active dams BEFORE coordinate assignment:")
print(filtered_active_dams[['willDam', 'Clean_names']])

# This is where the problem occurs - direct assignment by position
# Even if we had matches, the indices likely don't align
if len(filtered_active_dams) > 0 and len(active_dams) > 0:
    filtered_active_dams["lat"] = active_dams["Decimal degree latitude"]
    filtered_active_dams["long"] = active_dams["Decimal degree longitude"]
    print("\nFiltered active dams AFTER coordinate assignment (WRONG):")
    print(filtered_active_dams[['willDam', 'Clean_names', 'lat', 'long']])
else:
    print("\nNo matches found - demonstrating the core issue:")
    print("Clean_names contains:", filtered_dam_df["Clean_names"].tolist())
    print("Name of dam contains:", dam_location_SA["Name of dam"].tolist())
    print("^ These don't match exactly!")

# THE CORRECT APPROACH - FIRST FIX THE MATCHING, THEN ASSIGN PROPERLY
print("\n=== CORRECT APPROACH: FIX MATCHING FIRST ===")

# Option 1: Adjust the cleaning to match exactly
# Either keep full names in Clean_names, or strip "Dam" from Name of dam

# Let's create a proper matching key
# Option A: Use full names for matching
filtered_dam_df['Clean_names_full'] = filtered_dam_df['willDam']  # Keep full name

# Now find matches
active_dams_correct = dam_location_SA[dam_location_SA["Name of dam"].isin(filtered_dam_df['Clean_names_full'])]
filtered_active_dams_correct = filtered_dam_df[filtered_dam_df['Clean_names_full'].isin(active_dams_correct["Name of dam"])]

print(f"\nWith full name matching:")
print(f"Active dams count: {len(active_dams_correct)}")
print(f"Filtered active dams count: {len(filtered_active_dams_correct)}")

# Now properly assign coordinates using merge (not direct assignment)
if len(active_dams_correct) > 0:
    # Merge approach - safest way to join data
    merged_result = pd.merge(
        filtered_active_dams_correct,
        active_dams_correct[['Name of dam', 'Decimal degree latitude', 'Decimal degree longitude']],
        left_on='Clean_names_full',
        right_on='Name of dam',
        how='left'
    )

    print("\nAfter proper merge (CORRECT):")
    print(merged_result[['willDam', 'Clean_names_full', 'Decimal degree latitude', 'Decimal degree longitude']])

    # Or if you want to keep original column names:
    merged_result = merged_result.rename(columns={
        'Decimal degree latitude': 'lat',
        'Decimal degree longitude': 'long'
    })
    print("\nRenamed columns:")
    print(merged_result[['willDam', 'Clean_names_full', 'lat', 'long']])

# Option B: Strip "Dam" from dam_location_SA for matching
print("\n=== OPTION B: STRIP 'DAM' FOR MATCHING ===")
dam_location_SA_clean = dam_location_SA.copy()
dam_location_SA_clean['Name_clean'] = dam_location_SA_clean['Name of dam'].str.replace(' Dam', '', regex=False)

# Now match Clean_names (which has first word) with Name_clean
# But wait - Clean_names has just first word, Name_clean has full name without "Dam"
# Let's adjust Clean_names to also be comparable

# Actually, let's see what we really have:
print("Clean_names (first word only):", filtered_dam_df["Clean_names"].tolist())
print("Name of dam:", dam_location_SA["Name of dam"].tolist())

# Better approach: extract first word from Name of dam for matching
dam_location_SA['First_word'] = dam_location_SA['Name of dam'].str.split().str[0]
print("First word from Name of dam:", dam_location_SA['First_word'].tolist())

# Now these should match!
active_dams_by_first_word = dam_location_SA[dam_location_SA['First_word'].isin(filtered_dam_df["Clean_names"])]
filtered_active_dams_by_first_word = filtered_dam_df[filtered_dam_df["Clean_names"].isin(dam_location_SA['First_word'])]

print(f"\nMatching by first word:")
print(f"Active dams count: {len(active_dams_by_first_word)}")
print(f"Filtered active dams count: {len(filtered_active_dams_by_first_word)}")

# Now properly join using the first word as key
if len(active_dams_by_first_word) > 0:
    # Create mapping from first word to coordinates
    lat_map = dam_location_SA.set_index('First_word')['Decimal degree latitude']
    lon_map = dam_location_SA.set_index('First_word')['Decimal degree longitude']

    # Apply mapping
    final_df = filtered_active_dams_by_first_word.copy()
    final_df['lat'] = final_df['Clean_names'].map(lat_map)
    final_df['long'] = final_df['Clean_names'].map(lon_map)

    print("\nFinal result with correct coordinates:")
    print(final_df[['willDam', 'Clean_names', 'lat', 'long']])

print("\n=== KEY INSIGHTS ===")
print("1. Your original issue had TWO problems:")
print("   a) Matching issue: 'Bronkhorstspruit' != 'Bronkhorstspruit Dam'")
print("   b) Assignment issue: Even if matched, direct assignment by position fails if indices differ")
print("")
print("2. Solutions:")
print("   a) For matching: Either adjust your cleaning strategy or use proper vectorized string operations")
print("   b) For assignment: ALWAYS use merge() or map()/set_index() - NEVER direct assignment unless indices are guaranteed to match")
print("")
print("3. Recommended approach for your case:")
print("   - Create a clean key column in both DataFrames (e.g., first word or cleaned name)")
print("   - Use merge() or map() to join the data based on that key")
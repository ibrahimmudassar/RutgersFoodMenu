import json
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlsplit

import grequests
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm
import re

urls = []
urls_metadata = {}

# everything to iterate over
meals = ["Breakfast", "Lunch", "Dinner"]
locations = [
    "Livingston+Dining+Commons",
    "Busch+Dining+Hall",
    "Neilson+Dining+Hall",
    "The+Atrium",
]

# iterate from today through the next week
for single_date in (datetime.today() + timedelta(n) for n in range(6)):
    for meal in meals:
        for locationName in locations:

            url = f"https://menuportal23.dining.rutgers.edu/foodpronet/pickmenu.aspx?locationNum=04&locationName={locationName}&dtdate={single_date.strftime('%m/%d/%Y')}&activeMeal={meal}&sName=Rutgers+University+Dining"
            urls_metadata[url] = {}
            urls_metadata[url]["date"] = single_date.strftime("%m/%d/%Y")
            urls_metadata[url]["location"] = " ".join(locationName.split("+"))
            urls_metadata[url]["meal"] = meal
            urls.append(grequests.get(url))

offerings = []
for response in tqdm(grequests.imap(urls, size=100), total=len(urls)):
    soup = BeautifulSoup(response.content, "lxml")
    soup = soup.find("div", class_="menuBox")

    foods = soup.find_all(["h3", "fieldset"])

    # print(response)
    just_h3 = []
    fieldset_stratified = []
    temp = []
    for i in foods:
        if i.name == "h3" and len(temp) > 0:
            just_h3.append(i.text.replace("-", "").strip())
            fieldset_stratified.append(temp)
            temp = []
        elif i.name == "fieldset":
            temp.append(i)
    fieldset_stratified.append(temp)

    for h3, fieldset_list in zip(just_h3, fieldset_stratified):
        for fieldset in fieldset_list:
            offering = {}

            offering["place"] = h3
            offering["item"] = fieldset.find("div", class_="col-1").label["name"]
            offering["portion_size"] = (
                fieldset.find("div", class_="col-2").text.strip().replace(" ", " ")
            )
            offering["nutrition_info"] = (
                "https://menuportal23.dining.rutgers.edu/foodpronet/"
                + fieldset.find("div", class_="col-3").a["href"]
            )
            offering = urls_metadata[response.url] | offering

            offerings.append(offering)

# from all these links, we need to get the calories of all unique foods
foods = []
for o in offerings:
    parsed_url = dict(parse_qsl(urlsplit(o["nutrition_info"]).query))
    foods.append(parsed_url["RecNumAndPort"])

urls = []
for f in sorted(list(set(foods))):
    urls.append(
        f"https://menuportal23.dining.rutgers.edu/foodpronet/label.aspx?RecNumAndPort={f}"
    )

calories = []
for response in tqdm(
    grequests.imap([grequests.get(u) for u in urls], size=100), total=len(urls)
):
    try:
        soup = BeautifulSoup(response.text, "html.parser")
        calories.append(
            {
                "item": soup.find_all("h2")[2].text,
                "calories": int(
                    soup.find(string=re.compile("Calories\xa0")).text.replace(
                        "Calories\xa0", ""
                    )
                ),
            }
        )
    except AttributeError:
        print(url)

calories_df = pd.DataFrame(calories)
df = pd.DataFrame(offerings)
df = df.merge(calories_df, how="left", on="item")

parsed = json.loads(df.to_json(orient="records"))
with open("offerings.json", "w") as f:
    f.write(json.dumps(parsed, indent=4, sort_keys=True))

import requests

shapes = open('shapes.ttl','r').readlines()
edgelist_file = open('check-results.txt', 'w')

def in_schema(obj):
    schema = open('schema-v1.ttl','r')
    lines =  schema.readlines()
    for l in lines:
        if l.startswith(f"{obj} a "):
            schema.close()
            return True
    schema.close()
    return False


for number, line in enumerate(shapes):
    line = line.strip()
    if line.startswith("schema:"):
        obj = line.split(" ")[0]
        if not in_schema(obj):
            edgelist_file.write(f"{number+1}: {obj} does not exist in schema\n")
    elif line.startswith("rdfs:subClassOf"):
        obj = line.split(" ")[1]
        if not in_schema(obj):
            edgelist_file.write(f"{number+1}: {obj} does not exist in schema\n")
    elif line.startswith("ys:fromClass"):
        obj = line.split(" ")[1]
        obj = obj.replace(",", "")
        class_ = obj[3:]
        if requests.get(f"https://www.wikidata.org/wiki/{class_}").status_code != 200:
            edgelist_file.write(f"{number+1}: {obj} does not exist in wikidata\n")
    elif line.startswith("ys:fromProperty"):
        objs = line.split(" ")
        for obj in objs:
            if obj.startswith("wdt:"):
                prop = obj.replace(",", "")
                prop = prop[4:]
                if requests.get(f"https://www.wikidata.org/wiki/Property:{prop}").status_code != 200:
                    edgelist_file.write(f"{number+1}: {obj} does not exist in wikidata\n")
            elif obj.startswith("wd:"):
                prop = obj.replace(",", "")
                prop = prop[3:]
                if requests.get(f"https://www.wikidata.org/wiki/Property:{prop}").status_code != 200:
                    edgelist_file.write(f"{number+1}: {obj} does not exist in wikidata\n")
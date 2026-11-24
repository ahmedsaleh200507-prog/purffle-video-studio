"""Conservative named-location screening, never infer GPS from visual similarity.

Source metadata is evidence of a provider's claim, not proof of physical location.
No new data source, external requests or API quota.
"""
import re
import unicodedata

# Deliberately distinguish a region from an entire country: Brazil alone does
# not establish Amazon rainforest, and Africa alone does not establish Sahara.
REGIONS={
    "amazon":("amazon rainforest","amazon rain forest","amazon basin","amazonas","amazon rainforests","amazonian","amazonia","amazon forest","amazon jungle","amazon river","amazon regenwald","amazonas regenwald","amazonbecken","amazone","amazon ormani","floresta amazonica","selva amazonica"),
    "sahara":("sahara","saharan","sahara desert","saharawuste"),
    "antarctica":("antarctica","antarctic","antarktis","antarktika"),
    "arctic":("arctic","arktis","arctic ocean","arktischer ozean"),
    "himalayas":("himalaya","himalayas","himalayan"),
    "alps":("alps","alpine mountains","alpen","alpes"),
    "yellowstone":("yellowstone","yellowstone national park"),
    "hawaii":("hawaii","hawaiian","kilauea","mauna loa","hawai'i"),
    "great barrier reef":("great barrier reef","great barrier riff"),
    "nile":("nile river","river nile","nil fluss","nil delta","nile delta"),
    "everest":("mount everest","everest","sagarmatha"),
    "new york":("new york","manhattan","brooklyn","nyc"),
    "london":("london","londoner"),
    "paris":("paris","pariser"),
    "vienna":("vienna","wien","viyana"),
    "rome":("rome","rom","roma","roman city"),
    "tokyo":("tokyo","tokio"),
    "iceland":("iceland","island","islandic","isländisch"),
    "japan":("japan","japanese","japanisch"),
    "egypt":("egypt","egyptian","agypten","ägypten"),
    "brazil":("brazil","brasil","brasilien","brazilian"),
    "europe":("europe","european","europa","europaisch"),
    "africa":("africa","african","afrika","afrikanisch"),
    "australia":("australia","australian","australien"),
    "south america":("south america","south american","sudamerika","südamerika"),
    "north america":("north america","north american","nordamerika"),
}
# "island" in English and "rom" in technology are ambiguous, so exclude
# these stand-alone tokens. Exact city/region terms still remain available.
REGIONS["iceland"]=("iceland","icelandic","islandische","islandischer")
REGIONS["rome"]=("rome","roma","stadt rom","antikes rom")
PARENTS={"amazon":{"brazil","south america"},"sahara":{"egypt","africa"},"everest":{"himalayas"},
         "alps":{"europe"},"vienna":{"europe"},"rome":{"europe"},"paris":{"europe"},"london":{"europe"}}
def normalized(value):
    value=unicodedata.normalize("NFKD",str(value or "").casefold())
    return " ".join(re.findall(r"[a-z0-9]+","".join(c for c in value if not unicodedata.combining(c))))
def named_regions(text):
    clean=" "+normalized(text)+" "
    return {name for name,aliases in REGIONS.items()
            if any(" "+normalized(alias)+" " in clean for alias in aliases)}
def specific(names):
    return sorted(set(names)-set().union(*(PARENTS.get(n,set()) for n in names)))
def scene_requirement(plan,topic=""):
    plan=plan or {}
    fields=" ".join(str(plan.get(k) or "") for k in
        ("location","visual_search_query","visual_subject","object","title","time"))
    names=named_regions(fields)
    if not names:
        # A geographically anchored subject must not silently become a generic
        # forest, city or animal scene during search-query relaxation.
        names=named_regions(topic)
    return specific(names)
def geography_evidence(required,metadata):
    have=named_regions(metadata)
    # Every named region in a multi-place scene needs independent metadata.
    # Parent geography never substitutes for a more precise region.
    missing=sorted(set(required)-have)
    conflicting=sorted(have-set(required)-set().union(*(PARENTS.get(n,set()) for n in required))) if required else []
    return {"required":list(required),"provider_claims":sorted(have),"missing":missing,
            "other_regions":conflicting,"accepted":not missing and not conflicting,
            "method":"provider_metadata_named_region_not_independent_geolocation"}
def require_geography(required,metadata):
    proof=geography_evidence(required,metadata)
    if not proof["accepted"]:
        raise ValueError("geography_mismatch: missing="+",".join(proof["missing"])+
                         " conflicting="+",".join(proof["other_regions"]))
    return proof
def scoped_queries(queries,required):
    if not required:
        return list(queries)
    prefix=" ".join("Amazon rainforest" if n=="amazon" else n for n in required)
    return list(dict.fromkeys((q if set(required)<=named_regions(q) else prefix+" "+q)
                             for q in queries if q.strip()))

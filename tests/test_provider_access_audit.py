from provider_access_audit import scan

class Response:
    status_code=200
    def __init__(self,data):
        self.data=data
    def json(self):
        return self.data

def test_google_pagination_and_secret_not_reported():
    calls=[]
    def get(url,**kwargs):
        calls.append((url,kwargs))
        if len(calls)==1:
            return Response({"models":[{"name":"models/gemini-4-hydrogen","supportedGenerationMethods":["generateContent"]}],"nextPageToken":"next"})
        return Response({"models":[{"name":"models/gemini-3.8-flash","supportedGenerationMethods":["generateContent"]}]})
    row=scan("gemini",{"GEMINI_API_KEY":"supersecret"},get)
    assert row["status"]=="catalog_read"
    assert row["models"][0]["listed"] and row["models"][1]["listed"]
    assert calls[1][1]["params"]["pageToken"]=="next"
    assert "supersecret" not in str(row)
    assert calls[0][1]["allow_redirects"] is False

def test_openrouter_checks_actual_zero_price():
    def get(*a,**k):
        return Response({"data":[{"id":"nvidia/nemotron-3-ultra-550b-a55b:free","pricing":{"prompt":"0","completion":"0","request":"0.01"}}]})
    row=scan("openrouter",{"OPENROUTER_API_KEY":"test"},get)
    assert row["models"][0]["catalog_zero_pricing"] is False

def test_missing_key_no_calls():
    def forbidden(*a,**k):
        raise AssertionError("network call with no key")
    assert scan("groq",{},forbidden)["status"]=="key_missing"

def test_429_distinguished_from_missing_model():
    class Limited:
        status_code=429
    row=scan("groq",{"GROQ_API_KEY":"test"},lambda *a,**k:Limited())
    assert row["status"]=="rate_limited" and not row["models"]

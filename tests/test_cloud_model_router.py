import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from cloud_model_router import Router, MODELS, ModelError, validate_json
SCHEMA={"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":False}
MESSAGES=[{"role":"user","content":"Return JSON answer."}]
def response(code=200,content='{"answer":"ok"}',finish="stop"):
    return SimpleNamespace(status_code=code,json=lambda:{"choices":[{"finish_reason":finish,"message":{"content":content}}]})
class RouterTests(unittest.TestCase):
    def test_model_order_and_strict_schema(self):
        attempts=[]
        def send(url,**kw):
            attempts.append(kw["json"])
            return response(429) if len(attempts)==1 else response()
        r=Router({"GEMINI_API_KEY":"test","GROQ_API_KEY":"test"},send)
        self.assertEqual(json.loads(r.complete(MESSAGES,schema=SCHEMA)),{"answer":"ok"})
        self.assertEqual([p["model"] for p in attempts],[MODELS[0][1],MODELS[1][1]])
        self.assertTrue(attempts[1]["response_format"]["json_schema"]["strict"])
        self.assertEqual(attempts[1]["response_format"]["json_schema"]["schema"],SCHEMA)
    def test_invalid_json_falls_through(self):
        calls=[]
        def send(url,**kw):
            calls.append(kw["json"]["model"])
            return response(content='{"wrong":true}') if len(calls)==1 else response()
        r=Router({"GEMINI_API_KEY":"test","GROQ_API_KEY":"test"},send)
        self.assertEqual(json.loads(r.complete(MESSAGES,schema=SCHEMA)),{"answer":"ok"})
        self.assertEqual(len(calls),2)
    def test_daily_model_block_not_provider(self):
        calls=[]
        def send(url,**kw):
            calls.append(kw["json"]["model"])
            if len(calls)==1:
                return SimpleNamespace(status_code=429,json=lambda:{"error":{"message":"daily quota"}})
            return response(404) if len(calls)==2 else response()
        r=Router({"GEMINI_API_KEY":"test","GROQ_API_KEY":"test"},send)
        r.complete(MESSAGES,schema=SCHEMA)
        r.complete(MESSAGES,schema=SCHEMA)
        self.assertEqual(calls,[MODELS[0][1],MODELS[1][1],MODELS[2][1],MODELS[2][1]])
    def test_local_when_no_keys(self):
        r=Router({"PURFFLE_LOCAL_LLM":"1"})
        with patch("local_llm.complete_adaptive",return_value='{"answer":"ok"}') as m:
            r.complete(MESSAGES,schema=SCHEMA)
            self.assertEqual(m.call_args.kwargs["prefer"],"quality")
    def test_reject_bad_local_schema(self):
        with self.assertRaises(ModelError):
            validate_json('{"wrong":1}',SCHEMA)
if __name__=="__main__":unittest.main()

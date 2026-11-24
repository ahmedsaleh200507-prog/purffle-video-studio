import unittest
from unittest.mock import patch
from types import SimpleNamespace
from long_llm import get_long_client
from local_llm import enabled,local_completion

class LocalLLMTests(unittest.TestCase):
    def test_disabled_default(self):
        self.assertFalse(enabled({}))
    def test_no_keys_local_only(self):
        c=get_long_client(environ={"PURFFLE_LOCAL_LLM":"1"})
        with patch("local_llm.local_completion",return_value="local") as call:
            self.assertEqual(c.chat.completions.create(messages=[]),"local")
            call.assert_called_once()
    def test_cloud_errors_route_local(self):
        error=RuntimeError("quota")
        error.status_code=429
        groq=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(error))))
        c=get_long_client(groq=groq,environ={"PURFFLE_LOCAL_LLM":"1","GEMINI_API_KEY":"test"},
            post=lambda *a,**kw: SimpleNamespace(status_code=503))
        with patch("local_llm.local_completion",return_value="local") as call:
            self.assertEqual(c.chat.completions.create(messages=[]),"local")
            call.assert_called_once()
    def test_schema_preserved(self):
        schema={"type":"object"}
        with patch("local_llm.instance") as q:
            q.return_value.complete.return_value='{"ok":true}'
            result=local_completion(messages=[],response_format={"type":"json_schema","json_schema":{"schema":schema}})
            self.assertEqual(result.choices[0].message.content,'{"ok":true}')
            self.assertEqual(q.return_value.complete.call_args.kwargs["schema"],schema)
if __name__=="__main__": unittest.main()

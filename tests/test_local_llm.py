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
        with patch("local_llm.complete_adaptive") as q:
            q.return_value='{"ok":true}'
            result=local_completion(messages=[],response_format={"type":"json_schema","json_schema":{"schema":schema}})
            self.assertEqual(result.choices[0].message.content,'{"ok":true}')
            self.assertEqual(q.call_args.kwargs["schema"],schema)
    def test_quality_selection_and_schema(self):
        from local_llm import complete_adaptive
        with patch.dict("os.environ",{"PURFFLE_LOCAL_QUALITY":"1"}), patch("local_llm._INSTANCE",None), patch("local_llm.instance") as q:
            q.return_value.complete.return_value='{"ok":true}'
            self.assertEqual(complete_adaptive([],prefer="quality"),'{"ok":true}')
            q.assert_called_once_with("quality")
    def test_quality_failure_falls_back_to_fast(self):
        from local_llm import complete_adaptive
        with patch.dict("os.environ",{"PURFFLE_LOCAL_QUALITY":"1"}), patch("local_llm._INSTANCE",None), patch("local_llm.instance") as q:
            q.side_effect=[SimpleNamespace(complete=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("failed"))),
                           SimpleNamespace(complete=lambda *a,**k:'{"ok":true}')]
            self.assertEqual(complete_adaptive([],prefer="quality"),'{"ok":true}')
            self.assertEqual([x.args for x in q.call_args_list],[("quality",),("fast",)])
if __name__=="__main__": unittest.main()

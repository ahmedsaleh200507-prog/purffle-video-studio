from story_room import StoryRoom, CRITERIA

def test_rewrite_after_low_score():
    class FakeRoom(StoryRoom):
        def __init__(self):
            self.trace=[]
            self.calls=[]
        def ask(self,role,prompt,schema,preferred,**kw):
            self.calls.append(role)
            if role=="compare":
                return {"winner":0,"scores":[dict.fromkeys(CRITERIA,7),dict.fromkeys(CRITERIA,6)],"feedback":"Open with a concrete observation."},"editor"
            if role.startswith("final_editor"):
                score=7 if role.endswith("1") else 8
                return {"scores":dict.fromkeys(CRITERIA,score),"feedback":"Improve the opening."},"editor"
            return {"angle":"contrast","beats":["start","cause","result"],"narration":"Some volcanoes blast rock into the sky. Others erupt less violently. As magma rises, pressure falls and gas bubbles expand. Runny magma lets gas escape more easily. Sticky magma can trap gas, allowing pressure to build until an explosive eruption takes place."},"writer"
    room=FakeRoom()
    result=room.generate("Why do volcanoes erupt?","en","Reference text",word_range=(32,95))
    assert result["editorial_pass"]
    assert len(result["attempts"])==2
    assert not result["attempts"][0]["accepted"]
    assert result["attempts"][1]["different_models"]
    assert room.calls==["writer_1","writer_2","compare","rewrite_1","final_editor_1","rewrite_2","final_editor_2"]

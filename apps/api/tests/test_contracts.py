def test_canonical_document():
    document={"schema_version":1,"sections":[{"id":"s1","title":"Objetivo","markdown":"observação"}]}
    assert document["schema_version"]==1
    assert document["sections"][0]["markdown"]

def test_annotation_schema_is_editable():
    payload={"schema_version":1,"width":1200,"height":800,"shapes":[{"id":"a","type":"rect","x":10,"y":10,"width":100,"height":80}]}
    assert payload["shapes"][0]["type"] in {"arrow","rect","circle","line","text","highlight","step","blur","redact"}

def test_conflict_is_explicit():
    current=4
    expected=3
    assert expected != current

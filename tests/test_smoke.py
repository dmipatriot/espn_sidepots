import pandas as pd

def test_placeholder():
    df = pd.DataFrame({"a":[1,2]})
    assert len(df) == 2

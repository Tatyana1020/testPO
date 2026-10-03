import pytest

from main import add, get_message, main


def test_get_message():
    assert get_message() == "Hello, World!"


def test_main_output(capsys):
    main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "Hello, World!"


@pytest.mark.parametrize(
    "a,b,expected", 
    [(2, 3, 5), 
     (-1, 1, 0), 
     (0, 0, 0), 
     (100, 200, 300)
    ]
)
def test_add(a, b, expected):
    assert add(a, b) == expected

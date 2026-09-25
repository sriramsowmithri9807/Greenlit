from calculator import add, average, divide


def test_add():
    assert add(2, 3) == 5


def test_average():
    assert average([1, 2, 3]) == 2


def test_divide():
    assert divide(10, 2) == 5

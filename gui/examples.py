"""Небольшие примеры программ для GUI."""

EXAMPLES = {
    "Факториал": """\
n = 5;
result = 1;
i = 1;
while i <= n {
    result = result * i;
    i = i + 1;
}
""",
    "Фибоначчи": """\
n = 10;
a = 0;
b = 1;
i = 0;
while i < n {
    t = a + b;
    a = b;
    b = t;
    i = i + 1;
}
""",
    "НОД": """\
a = 48;
b = 18;
while b != 0 {
    t = b;
    b = a % b;
    a = t;
}
""",
    "Вложенные условия": """\
x = 7;
if x > 5 {
    if x > 6 {
        y = 1;
    } else {
        y = 2;
    }
} else {
    y = 3;
}
""",
    "Массивы": """\
int squares[5];
i = 0;
while i < 5 {
    squares[i] = i * i;
    i = i + 1;
}
sum = 0;
i = 0;
while i < 5 {
    sum = sum + squares[i];
    i = i + 1;
}
""",
}

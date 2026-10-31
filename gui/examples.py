"""Небольшие примеры программ для GUI.

В языке переменная обязана быть объявлена (``int x;``) до первого
использования, а области видимости нет: объявление действует до конца
программы. Поэтому переменные, которые нужны внутри цикла, объявляются
перед циклом.
"""

EXAMPLES = {
    "Факториал": """\
int n = 5;
int result = 1;
int i = 1;
while i <= n {
    result = result * i;
    i = i + 1;
}
print("факториал", n, "равен", result);
""",
    "Фибоначчи": """\
int n = 10;
int a = 0;
int b = 1;
int i = 0;
int t = 0;
while i < n {
    t = a + b;
    a = b;
    b = t;
    i = i + 1;
}
print("a =", a, "b =", b);
""",
    "НОД": """\
int a = 48;
int b = 18;
int t = 0;
while b != 0 {
    t = b;
    b = a % b;
    a = t;
}
print("НОД =", a);
""",
    "Вложенные условия": """\
int x = 7;
int y = 0;
if x > 5 {
    if x > 6 {
        y = 1;
    } else {
        y = 2;
    }
} else {
    y = 3;
}
print("y =", y);
""",
    "Массивы": """\
int squares[5];
int i = 0;
int sum = 0;
while i < 5 {
    squares[i] = i * i;
    i = i + 1;
}
i = 0;
while i < 5 {
    sum = sum + squares[i];
    i = i + 1;
}
print("сумма квадратов =", sum);
""",
    "Вещественные числа": """\
double pi = 3.14159;
float half = 0.5f;
double r = 2.0;
double area = pi * r * r;
print("площадь круга =", area);
print("половина =", half);
print("корень из 2 =", sqrt(2));
""",
    "Строки": """\
string greeting = "привет";
string name = "мир";
string message = greeting + ", " + name + "!";
print(message);
print("длина сравнения:", message == greeting);
""",
    "Функции": """\
func int fact(int n) {
    if n <= 1 {
        return 1;
    }
    return n * fact(n - 1);
}

func int twice(int x) {
    return x * 2;
}

int f = fact(5);
print("5! =", f);
print("2 * 21 =", twice(21));
""",
    "Горутины": """\
func int count(int n) {
    int i = 0;
    int s = 0;
    while i < n {
        s = s + i;
        i = i + 1;
    }
    return s;
}

go worker = count(1000);
go other = count(10);
sync();
print("горутины закончились");
""",
}

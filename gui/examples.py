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
    "Ввод и вывод": """\
string name = input("Как вас зовут? ");
int age = int(input("Сколько вам лет? "));
print("Привет,", name + "! Через год вам будет", age + 1);
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
    "Графика: дом": """\
linewidth(2);
color("black");
rect(120, 160, 400, 360);
line(120, 160, 260, 60);
line(260, 60, 400, 160);
rect(240, 250, 300, 360);
rect(150, 200, 200, 250);
circle(350, 225, 25);
color("blue");
text(150, 380, "Дом");
""",
    "Графика: парабола": """\
color("blue");
linewidth(2);
int x = -300;
int y = 0;
while x <= 300 {
    y = x * x / 1000;
    point(320 + x, 430 - y);
    x = x + 5;
}
""",
    "Графика: узор": """\
linewidth(2);
int i = 0;
while i < 12 {
    if i % 2 == 0 {
        color("red");
    } else {
        color("blue");
    }
    circle(320, 240, 20 + i * 15);
    i = i + 1;
}
""",
    "Мандельбрум: траектория одной точки": """\
double cx = -0.6;
double cy = 0.3;
double zx = 0.0;
double zy = 0.0;
double x = 0.0;
double y = 0.0;
int i = 0;
int max_iter = 256;
linewidth(3);
line(120.0, 240.0, 520.0, 240.0);
line(320.0, 40.0, 320.0, 440.0);
while i < max_iter {
    x = zx * zx - zy * zy + cx;
    y = 2 * zx * zy + cy;
    if x * x + y * y > 4 {
        i = max_iter - 1;
    }
    line(x * 100.0 + 320, y * 100.0 + 240, zx * 100.0 + 320, zy * 100.0 + 240);
    zx = x;
    zy = y;
    i = i + 1;
}
""",
    "Мандельбрум: несколько траекторий": """\
string col1 = "red";
string col2 = "blue";
string col3 = "green";
string col4 = "purple";
string col5 = "orange";
string col6 = "cyan";

func int draw_trajectory(double cx, double cy, string col) {
    color(col);
    double zx = 0.0;
    double zy = 0.0;
    double x = 0.0;
    double y = 0.0;
    int i = 0;
    while i < 256 {
        x = zx * zx - zy * zy + cx;
        y = 2 * zx * zy + cy;
        if x * x + y * y > 4 {
            i = 255;
        }
        line(x * 100.0 + 320, y * 100.0 + 240, zx * 100.0 + 320, zy * 100.0 + 240);
        zx = x;
        zy = y;
        i = i + 1;
    }
    return 0;
}

linewidth(3);
color("black");
line(120.0, 240.0, 520.0, 240.0);
line(320.0, 40.0, 320.0, 440.0);
go t1 = draw_trajectory(-0.6, 0.3, col1);
go t2 = draw_trajectory(-0.4, -0.8, col2);
go t3 = draw_trajectory(0.5, 0.0, col3);
go t4 = draw_trajectory(0.35, 0.8, col4);
go t5 = draw_trajectory(-1.3, 0.7, col5);
go t6 = draw_trajectory(0.9, -0.7, col6);
sync();
""",
    "Мандельбрум: множество": """\
func int iterate(double cx, double cy, int max_iter) {
    double zx = 0.0;
    double zy = 0.0;
    double x = 0.0;
    double y = 0.0;
    int i = 0;
    int escaped = 0;
    while i < max_iter {
        x = zx * zx - zy * zy + cx;
        y = 2 * zx * zy + cy;
        if x * x + y * y > 4 {
            escaped = 1;
            i = max_iter;
        }
        zx = x;
        zy = y;
        i = i + 1;
    }
    if escaped == 1 {
        return 1;
    }
    return 0;
}

int gx = 0;
int gy = 0;
int max_iter = 30;
while gx <= 30 {
    gy = 0;
    while gy <= 24 {
        if iterate(gx * 0.1 - 2.0, gy * 0.1 - 1.2, max_iter) == 0 {
            point((gx * 0.1 - 2.0 + 2) * 200 + 20, (1.2 - (gy * 0.1 - 1.2)) * 150 + 20);
        }
        gy = gy + 1;
    }
    gx = gx + 1;
}
""",
    "Потоки и время": """\
func int wait_second() {
    double start = time();
    while time() - start < 1.0 {
    }
    return 1;
}

double t0 = time();
go a = wait_second();
go b = wait_second();
sync();
print("два потока ждали по секунде, заняло", time() - t0, "с");
""",
}

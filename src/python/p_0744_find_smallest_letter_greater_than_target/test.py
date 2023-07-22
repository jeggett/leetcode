from math import sqrt

a = float(input())
b = float(input())
c = float(input())

d = b**2 - 4 * a * c

if a == 0 and b == 0 and c == 0:
    print("Infinite solutions")
elif a == 0 and b != 0:
    print("{:.2f}".format(-c / b))
elif d < 0 or a == 0 and b == 0 and c != 0:
    print("No solution")
else:
    roots = sorted([(-b - sqrt(d)) / (2 * a), (-b + sqrt(d)) / (2 * a)])
    if roots[0] == roots[1]:
        del roots[1]
    for root in roots:
        print("{:.2f} ".format(root), end="")

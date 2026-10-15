class Solution:
    def kidsWithCandies(self, candies: list[int], extraCandies: int) -> list[bool]:
        maximum = max(candies)
        return list(map(lambda num: (num + extraCandies) >= maximum, candies))

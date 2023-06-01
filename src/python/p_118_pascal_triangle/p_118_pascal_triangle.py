from typing import List


class Solution:
    '''time O(N^2), space O(1)'''
    def generate(self, numRows: int) -> List[List[int]]:
        result = [[1]]
        if numRows == 1:
            return result

        result.append([1, 1])

        if numRows == 2:
            return result

        for current_row in range(3, numRows + 1):
            newRow = [1]
            for i in range(1, current_row - 1):
                newRow.append(result[-1][i - 1] + result[-1][i])
            newRow.append(1)
            result.append(newRow)

        return result

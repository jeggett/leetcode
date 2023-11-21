// time O(n), space O(n)
export function missingNumberHashMap(nums: number[]): number {
  const markerArr: Uint8Array = new Uint8Array(nums.length + 1);
  for (const num of nums) {
    markerArr[num] = 1;
  }
  for (let index = 0; index < markerArr.length - 1; index++) {
    if (markerArr[index] === 0) {
      return index;
    }
  }

  return markerArr.length - 1;
}

// follow up using sum of interger series
// time O(n), space O(1)
export function missingNumberSum(nums: number[]): number {
  let sumOfSeries: number = (nums.length * (nums.length + 1)) / 2;
  for (const num of nums) {
    sumOfSeries -= num;
  }

  return sumOfSeries;
}

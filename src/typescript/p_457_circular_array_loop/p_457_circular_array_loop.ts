function getNextIndex(
  currentIndex: number,
  increment: number,
  arraySize: number,
): number {
  const newIndex = (currentIndex + increment) % arraySize;
  return newIndex < 0 ? arraySize + newIndex : newIndex;
}
function isNotCycle(
  nums: number[],
  currentPointer: number,
  initialDirection: number,
) {
  const directionsMismatch = initialDirection * nums[currentPointer] < 0;

  return (
    getNextIndex(currentPointer, nums[currentPointer], nums.length) ===
      currentPointer || directionsMismatch
  );
}

/* time: O(n), space: O(1) */
export function circularArrayLoop(nums: number[]): boolean {
  const arraySize = nums.length;
  for (let i = 0; i < arraySize; i++) {
    let slowPointer = i;
    let fastPointer = i;
    const initialDirection = nums[i];

    while (true) {
      slowPointer = getNextIndex(slowPointer, nums[slowPointer], arraySize);
      if (isNotCycle(nums, slowPointer, initialDirection)) {
        break;
      }

      fastPointer = getNextIndex(fastPointer, nums[fastPointer], arraySize);
      if (isNotCycle(nums, fastPointer, initialDirection)) {
        break;
      }
      fastPointer = getNextIndex(fastPointer, nums[fastPointer], arraySize);
      if (isNotCycle(nums, fastPointer, initialDirection)) {
        break;
      }

      if (slowPointer === fastPointer) {
        return true;
      }
    }
  }

  return false;
}

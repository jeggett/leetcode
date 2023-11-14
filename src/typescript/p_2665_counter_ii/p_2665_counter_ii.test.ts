import { createCounter } from "./p_2665_counter_ii";

test("problem 2665", () => {
  const counter = createCounter(5);
  expect(counter.increment()).toEqual(6);
  expect(counter.reset()).toEqual(5);
  expect(counter.decrement()).toEqual(4);
});

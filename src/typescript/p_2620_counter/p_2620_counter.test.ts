import { createCounter } from "./p_2620_counter.js";

test("problem 2620", () => {
    const counter = createCounter(5);
    expect(counter()).toEqual(5);
    expect(counter()).toEqual(6);
});

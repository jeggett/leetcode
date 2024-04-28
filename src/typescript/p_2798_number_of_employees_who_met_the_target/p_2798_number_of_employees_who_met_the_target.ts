export function numberOfEmployeesWhoMetTarget(hours: number[], target: number): number {
    let counter = 0;
    hours.forEach((hours_worked) => {
        if (hours_worked >= target) {
            counter += 1;
        }
    });
    return counter;
}

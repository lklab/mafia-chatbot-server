import random
from collections import defaultdict

class CodeGenerator:
    def __init__(self, min_digits: int):
        self.min_digits = min_digits
        self.current_digits = min_digits
        self.issued_codes = defaultdict(set)
        self.total_codes = lambda digits: 10 ** digits

    def _get_utilization(self, digits):
        return len(self.issued_codes[digits]) / self.total_codes(digits)

    def _update_current_digits(self):
        while self._get_utilization(self.current_digits) >= 0.1:
            self.current_digits += 1
        
    def issueCode(self) -> str:
        self._update_current_digits()
        digits = self.current_digits
        total_possibilities = self.total_codes(digits)

        if len(self.issued_codes[digits]) >= total_possibilities:
            raise Exception("All possible codes are exhausted for the current digits.")

        while True:
            code = f"{random.randint(0, total_possibilities - 1):0{digits}}"
            if code not in self.issued_codes[digits]:
                self.issued_codes[digits].add(code)
                return code

    def returnCode(self, code: str):
        digits = len(code)
        if code in self.issued_codes[digits]:
            self.issued_codes[digits].remove(code)
        
        # Update current digits to the smallest utilization below 10%
        for d in range(self.min_digits, self.current_digits + 1):
            if self._get_utilization(d) < 0.1:
                self.current_digits = d
                break

# Example Usage
if __name__ == "__main__":
    cg = CodeGenerator(min_digits=4)

    codes = [cg.issueCode() for _ in range(15)]
    print("Issued Codes:", codes)

    for i in range(5) :
        cg.returnCode(codes[i])
        print(f"Returned Code: {codes[i]}")

    codes = [cg.issueCode() for _ in range(15)]
    print("Issued Codes:", codes)

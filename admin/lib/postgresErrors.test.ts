import { describe, expect, it } from "vitest";
import { translatePriceRuleError } from "./postgresErrors";

describe("translatePriceRuleError", () => {
  it("maps a known CHECK violation to its Arabic message", () => {
    const raw =
      'new row for relation "price_rules" violates check constraint ' +
      '"price_rules_min_profit_bands_valid"';
    expect(translatePriceRuleError(raw)).toBe(
      "فترات حد الربح الأدنى غير مكتملة أو متداخلة أو فيها فجوة — راجع الفترات وحاول مرة أخرى."
    );
  });

  it("maps a known UNIQUE violation to its Arabic message", () => {
    const raw =
      'duplicate key value violates unique constraint "price_rules_single_global"';
    expect(translatePriceRuleError(raw)).toBe(
      "توجد قاعدة عامة واحدة بالفعل — لا يمكن إنشاء أخرى."
    );
  });

  it("falls back to the generic message for an unrecognized constraint name", () => {
    const raw = 'violates check constraint "some_future_constraint_nobody_mapped_yet"';
    expect(translatePriceRuleError(raw)).toBe(
      "تعذر حفظ القاعدة — تحقق من صحة القيم المدخلة."
    );
  });

  it("falls back to the generic message for a non-constraint error", () => {
    expect(translatePriceRuleError("not permitted to update this price rule")).toBe(
      "تعذر حفظ القاعدة — تحقق من صحة القيم المدخلة."
    );
  });

  it("never echoes the raw English message back for a matched constraint", () => {
    const raw = 'violates check constraint "price_rules_global_always_active"';
    const translated = translatePriceRuleError(raw);
    expect(translated).not.toContain("violates");
    expect(translated).not.toContain("constraint");
  });
});

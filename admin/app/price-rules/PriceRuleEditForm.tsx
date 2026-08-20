"use client";

import { useState } from "react";
import {
  validateLeadTimeBands,
  validateOccupancyBands,
  type BandValidationResult,
} from "@/lib/priceRuleBands";
import type {
  DemandCurve,
  MinProfitByLeadTime,
  PriceRuleForDashboard,
  PriceRuleScope,
} from "@/lib/types";
import { BandRowsEditor, type GenericBand } from "./BandRowsEditor";
import { setPriceRuleActive, upsertPriceRule } from "./actions";

const DEFAULT_MIN_PROFIT: MinProfitByLeadTime = {
  bands: [{ min_lead_days: 0, max_lead_days: null, min_profit_halalas: 0 }],
};

const DEFAULT_DEMAND_CURVE: DemandCurve = {
  occupancy_bands: [{ min: 0, max: 1, multiplier_bps: 10000 }],
  lead_time_bands: [{ min_lead_days: 0, max_lead_days: null, multiplier_bps: 10000 }],
};

function toGeneric(
  bands: { min_lead_days: number; max_lead_days: number | null; min_profit_halalas: number }[]
): GenericBand[];
function toGeneric(
  bands: { min_lead_days: number; max_lead_days: number | null; multiplier_bps: number }[]
): GenericBand[];
function toGeneric(bands: { min: number; max: number; multiplier_bps: number }[]): GenericBand[];
function toGeneric(bands: Record<string, unknown>[]): GenericBand[] {
  return bands.map((band) => ({
    min: (band.min_lead_days ?? band.min) as number,
    max: (band.max_lead_days !== undefined ? band.max_lead_days : band.max) as number | null,
    value: (band.min_profit_halalas ?? band.multiplier_bps) as number,
  }));
}

interface PriceRuleEditFormProps {
  rule: PriceRuleForDashboard | null;
  scope: PriceRuleScope;
  scopeId: number | null;
  scopeLabel: string;
  onSaved: () => void;
}

// Every non-global scope's three fields are individually either "inherit
// from the next less specific scope" (send null — ARCHITECTURE.md's
// field-by-field design) or "override at this scope" (send the edited
// value) — admin_upsert_price_rule is a whole-row replace, so this form
// has to make that choice explicit per field rather than only ever
// sending a value. The global rule has no less specific scope to inherit
// from (price_rules_global_is_complete requires it to set everything), so
// its three fields are always in "override" mode.
export function PriceRuleEditForm({
  rule,
  scope,
  scopeId,
  scopeLabel,
  onSaved,
}: PriceRuleEditFormProps) {
  const isGlobal = scope === "global";

  const [overrideMargin, setOverrideMargin] = useState(
    isGlobal || rule?.target_margin_bps !== null
  );
  const [marginBps, setMarginBps] = useState(rule?.target_margin_bps ?? 0);

  const [overrideMinProfit, setOverrideMinProfit] = useState(
    isGlobal || rule?.min_profit_by_lead_time !== null
  );
  const [minProfitBands, setMinProfitBands] = useState<GenericBand[]>(
    toGeneric((rule?.min_profit_by_lead_time ?? DEFAULT_MIN_PROFIT).bands)
  );

  // demand_curve is never masked and never null on an existing row (see
  // PriceRuleForDashboard) — it always has a real value to seed the form
  // with, existing rule or not.
  const [overrideDemandCurve, setOverrideDemandCurve] = useState(isGlobal || rule !== null);
  const [occupancyBands, setOccupancyBands] = useState<GenericBand[]>(
    toGeneric((rule ?? { demand_curve: DEFAULT_DEMAND_CURVE }).demand_curve.occupancy_bands)
  );
  const [demandLeadTimeBands, setDemandLeadTimeBands] = useState<GenericBand[]>(
    toGeneric((rule ?? { demand_curve: DEFAULT_DEMAND_CURVE }).demand_curve.lead_time_bands)
  );

  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const minProfitValidation: BandValidationResult | null = overrideMinProfit
    ? validateLeadTimeBands(
        minProfitBands.map((b) => ({
          min_lead_days: b.min,
          max_lead_days: b.max,
          min_profit_halalas: b.value,
        })),
        "min_profit_halalas",
        "حد الربح الأدنى"
      )
    : null;
  const demandLeadTimeValidation: BandValidationResult | null = overrideDemandCurve
    ? validateLeadTimeBands(
        demandLeadTimeBands.map((b) => ({
          min_lead_days: b.min,
          max_lead_days: b.max,
          multiplier_bps: b.value,
        })),
        "multiplier_bps",
        "مضاعِف مدة الحجز"
      )
    : null;
  const occupancyValidation: BandValidationResult | null = overrideDemandCurve
    ? validateOccupancyBands(
        occupancyBands.map((b) => ({ min: b.min, max: b.max, multiplier_bps: b.value }))
      )
    : null;

  const liveError =
    minProfitValidation && !minProfitValidation.valid
      ? minProfitValidation.message
      : demandLeadTimeValidation && !demandLeadTimeValidation.valid
        ? demandLeadTimeValidation.message
        : occupancyValidation && !occupancyValidation.valid
          ? occupancyValidation.message
          : null;

  async function handleSave(): Promise<void> {
    setError(null);
    if (liveError) {
      setError(liveError);
      return;
    }
    if (isGlobal && (!overrideMargin || !overrideMinProfit || !overrideDemandCurve)) {
      setError(
        "القاعدة العامة أساس سلسلة التوريث — يجب تحديد الهامش وحد الربح الأدنى ومنحنى الطلب معاً."
      );
      return;
    }
    setSaving(true);
    const result = await upsertPriceRule(
      scope,
      scopeId,
      overrideMargin ? marginBps : null,
      overrideMinProfit
        ? {
            bands: minProfitBands.map((b) => ({
              min_lead_days: b.min,
              max_lead_days: b.max,
              min_profit_halalas: b.value,
            })),
          }
        : null,
      overrideDemandCurve
        ? {
            occupancy_bands: occupancyBands.map((b) => ({
              min: b.min,
              max: b.max ?? 1,
              multiplier_bps: b.value,
            })),
            lead_time_bands: demandLeadTimeBands.map((b) => ({
              min_lead_days: b.min,
              max_lead_days: b.max,
              multiplier_bps: b.value,
            })),
          }
        : null
    );
    setSaving(false);
    if (result.error) {
      setError(result.error);
      return;
    }
    onSaved();
  }

  async function handleToggleActive(nextActive: boolean): Promise<void> {
    if (rule === null) {
      return;
    }
    setError(null);
    const result = await setPriceRuleActive(rule.id, nextActive);
    if (result.error) {
      setError(result.error);
      return;
    }
    onSaved();
  }

  return (
    <div>
      <h3>{scopeLabel}</h3>
      {error && <p role="alert">{error}</p>}

      {!isGlobal && rule !== null && (
        <p>
          {rule.is_active ? (
            <button type="button" onClick={() => handleToggleActive(false)}>
              تعطيل هذه القاعدة
            </button>
          ) : (
            <button type="button" onClick={() => handleToggleActive(true)}>
              تفعيل هذه القاعدة
            </button>
          )}
          {!rule.is_active && (
            <strong> — هذه القاعدة معطَّلة ولا تؤثر على التسعير حالياً.</strong>
          )}
        </p>
      )}

      <fieldset>
        <legend>الهامش المستهدف</legend>
        {!isGlobal && (
          <label>
            <input
              type="checkbox"
              checked={overrideMargin}
              onChange={(event) => setOverrideMargin(event.target.checked)}
            />
            تخصيص لهذا النطاق (بدل الوراثة من النطاق الأعم)
          </label>
        )}
        {overrideMargin && (
          <label>
            الهامش (نقطة أساس، 10000 = 100%)
            <input
              type="number"
              min={0}
              step={1}
              value={marginBps}
              onChange={(event) => setMarginBps(Number(event.target.value))}
            />
          </label>
        )}
      </fieldset>

      <fieldset>
        <legend>حد الربح الأدنى حسب مدة الحجز</legend>
        {!isGlobal && (
          <label>
            <input
              type="checkbox"
              checked={overrideMinProfit}
              onChange={(event) => setOverrideMinProfit(event.target.checked)}
            />
            تخصيص لهذا النطاق
          </label>
        )}
        {overrideMinProfit && (
          <BandRowsEditor
            bands={minProfitBands}
            onChange={setMinProfitBands}
            valueLabel="الحد الأدنى للربح (هللة)"
            allowOpenEnded
          />
        )}
      </fieldset>

      <fieldset>
        <legend>منحنى الطلب</legend>
        {!isGlobal && (
          <label>
            <input
              type="checkbox"
              checked={overrideDemandCurve}
              onChange={(event) => setOverrideDemandCurve(event.target.checked)}
            />
            تخصيص لهذا النطاق
          </label>
        )}
        {overrideDemandCurve && (
          <>
            <h4>حسب نسبة الإشغال (0 إلى 1)</h4>
            <BandRowsEditor
              bands={occupancyBands}
              onChange={setOccupancyBands}
              valueLabel="المضاعِف (نقطة أساس)"
              allowOpenEnded={false}
              step={0.01}
            />
            <h4>حسب مدة الحجز</h4>
            <BandRowsEditor
              bands={demandLeadTimeBands}
              onChange={setDemandLeadTimeBands}
              valueLabel="المضاعِف (نقطة أساس)"
              allowOpenEnded
            />
          </>
        )}
      </fieldset>

      <button type="button" onClick={handleSave} disabled={saving}>
        {saving ? "جارٍ الحفظ…" : "حفظ"}
      </button>
    </div>
  );
}

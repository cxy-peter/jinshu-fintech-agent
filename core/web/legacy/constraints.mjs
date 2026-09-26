/** Bounded additive retrieval hints. They never replace the user's request. */
export const normalize = value => String(value ?? '').normalize('NFKC').toLowerCase().trim();
export function protectedTerms(text) {
  const s = normalize(text);
  return [...new Set(s.match(/\d+(?:[.,:/-]\d+)*(?:\s*%|\s*个工作日|\s*天|\s*万元|\s*元)?|[a-z]+[-_]?[a-z]*\d+[a-z0-9_-]*|\b(?:iban|kyc|kyb|t\+1|fof|etf)\b/g) || [])].sort();
}
const unsafe = /https?:|<|>|忽略.{0,12}(指令|要求)|系统提示|system\s*prompt|ignore.{0,16}instruction/i;
const negation = /不包括|不包含|不要|不能|不得|不允许|没有|未提供|未满|排除|without|\bnot\b|\bnever\b/i;
export function checkHint(original, hint) {
  if (typeof hint !== 'string' || hint.length > 100) return '提示词长度或类型不合法';
  if (!hint.trim()) return null;
  if (unsafe.test(hint)) return '检索扩展不能包含地址、指令或标记';
  const before = protectedTerms(original);
  if (protectedTerms(hint).some(x => !before.includes(x))) return '扩展不得新增数字、产品编码或受保护实体';
  if (negation.test(hint)) return '扩展不得新增否定或排除条件';
  return null;
}
export function retrievalPlan(original, hints = []) {
  const accepted = [], rejected = [];
  for (const hint of hints.slice(0, 2)) {
    const reason = checkHint(original, hint);
    if (reason) rejected.push({hint, reason});
    else if (hint.trim() && !accepted.includes(hint.trim())) accepted.push(hint.trim());
  }
  return {original, accepted, rejected, protected: protectedTerms(original), originalRetained: true};
}

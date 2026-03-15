export function likeLabel(value: -1 | 0 | 1): string {
  if (value === 1) {
    return '喜欢';
  }
  if (value === -1) {
    return '不喜欢';
  }
  return '无信息';
}

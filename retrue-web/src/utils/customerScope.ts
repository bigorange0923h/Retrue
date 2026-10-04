/** 客户切换作用域：写操作捕获目标，旧请求即使在 A→B→A 后返回也不能改新页面。 */
export function createCustomerScope() {
  let version = 0
  let customerId = 0
  return {
    reset(id: number) { customerId = id; version += 1 },
    capture() { return { customerId, version } },
    isCurrent(snapshot: { customerId: number; version: number }) {
      return snapshot.customerId === customerId && snapshot.version === version
    },
  }
}

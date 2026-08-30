/** PC 与移动端共用的导航信息架构配置。 */

/** 主导航项。 */
export interface MainNavigationItem {
  name: 'dashboard' | 'customer-list' | 'schedule' | 'profile'
  path: string
  label: string
  icon: string
  activePrefixes: string[]
  activeRouteNames?: string[]
}

/** “我的 / 用户菜单”中的低频功能入口。 */
export interface ManagementNavigationItem {
  name: 'course-types' | 'knowledge' | 'accounts'
  label: string
  description: string
  icon: string
  adminOnly?: boolean
}

/** 高频业务入口：两端保持相同顺序，呈现方式分别为侧栏和底部导航。 */
export const mainNavigationItems: MainNavigationItem[] = [
  {
    name: 'dashboard',
    path: '/',
    label: '首页',
    icon: 'HomeFilled',
    activePrefixes: ['/'],
    activeRouteNames: ['dashboard'],
  },
  {
    name: 'customer-list',
    path: '/customers',
    label: '客户',
    icon: 'User',
    activePrefixes: ['/customers'],
  },
  {
    name: 'schedule',
    path: '/schedule',
    label: '课表',
    icon: 'Calendar',
    activePrefixes: ['/schedule'],
  },
  {
    name: 'profile',
    path: '/profile',
    label: '我的',
    icon: 'UserFilled',
    activePrefixes: ['/profile', '/course-types', '/knowledge', '/accounts'],
  },
]

/** 低频配置统一归入 PC 用户下拉和移动端“我的”。 */
export const managementNavigationItems: ManagementNavigationItem[] = [
  {
    name: 'course-types',
    label: '课程模板与计划模板',
    description: '维护单课程和可复用的组合课程计划',
    icon: 'Notebook',
  },
  {
    name: 'knowledge',
    label: '客户知识库',
    description: '客户私有知识条目与 AI 问答',
    icon: 'Reading',
  },
  {
    name: 'accounts',
    label: '账号管理',
    description: '管理系统用户与权限',
    icon: 'Setting',
    adminOnly: true,
  },
]

/** 判断当前页面是否属于指定主导航项。 */
export function isMainNavigationActive(
  item: MainNavigationItem,
  routeName: string | symbol | null | undefined,
  routePath: string,
): boolean {
  if (item.activeRouteNames?.includes(String(routeName))) return true
  if (item.name === 'dashboard') return routePath === '/'
  return item.activePrefixes.some((prefix) => routePath.startsWith(prefix))
}

/** 按当前用户权限过滤管理入口。 */
export function getVisibleManagementItems(isSuperuser: boolean): ManagementNavigationItem[] {
  return managementNavigationItems.filter((item) => !item.adminOnly || isSuperuser)
}

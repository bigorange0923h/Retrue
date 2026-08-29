/** 响应式视口状态：同一路由根据宽度切换 PC 与移动端页面。 */

import { onBeforeUnmount, onMounted, ref } from 'vue'

const MOBILE_MEDIA_QUERY = '(max-width: 767px)'

/** 返回实时移动端状态；平板及以上沿用 PC 页面。 */
export function useViewport() {
  const isMobile = ref(typeof window !== 'undefined' && window.matchMedia(MOBILE_MEDIA_QUERY).matches)
  let mediaQuery: MediaQueryList | undefined

  /** 同步媒体查询结果，兼容浏览器窗口缩放与设备旋转。 */
  function updateViewport(): void {
    isMobile.value = mediaQuery?.matches ?? false
  }

  onMounted(() => {
    mediaQuery = window.matchMedia(MOBILE_MEDIA_QUERY)
    updateViewport()
    mediaQuery.addEventListener('change', updateViewport)
  })

  onBeforeUnmount(() => {
    mediaQuery?.removeEventListener('change', updateViewport)
  })

  return { isMobile }
}

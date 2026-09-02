<script lang="ts">
/**
 * 业务卡片统一分发组件：按卡片类型渲染对应卡片，并把操作事件透传给父级。
 */

import { defineComponent } from 'vue'
import type { AssistantCard } from '@/api/assistant'
import type { AssistantCustomerMatch } from '@/types/api'
import CustomerSelectionCard from './CustomerSelectionCard.vue'
import CustomerSummaryCard from './CustomerSummaryCard.vue'
import DomainDraftCard from './DomainDraftCard.vue'
import RiskReviewCard from './RiskReviewCard.vue'
import TrainingDraftCard from './TrainingDraftCard.vue'

const TYPE_MAP = {
  customer_selection: CustomerSelectionCard,
  customer_summary: CustomerSummaryCard,
  training_draft: TrainingDraftCard,
  assessment_draft: DomainDraftCard,
  domain_draft: DomainDraftCard,
  risk_review: RiskReviewCard,
} as const

export default defineComponent({
  name: 'AssistantCardRenderer',
  components: { CustomerSelectionCard, CustomerSummaryCard, TrainingDraftCard, DomainDraftCard, RiskReviewCard },
  props: {
    card: { type: Object as () => AssistantCard, required: true },
    customerId: { type: Number as () => number | null, default: null },
    courseSessionId: { type: Number as () => number | null, default: null },
  },
  emits: ['selectCustomer', 'cardAction', 'confirmed', 'cancelled'],
  setup(props, { emit }) {
    const componentFor = (card: AssistantCard) => TYPE_MAP[card.type] ?? DomainDraftCard
    const cardProps = (card: AssistantCard) => ({ card, customerId: props.customerId, courseSessionId: props.courseSessionId })

    const onSelect = (candidate: AssistantCustomerMatch) => emit('selectCustomer', props.card, candidate)
    const onAction = (action: string) => emit('cardAction', props.card, action)
    const onConfirmed = () => emit('confirmed', props.card)
    const onCancelled = () => emit('cancelled', props.card)

    return { componentFor, cardProps, onSelect, onAction, onConfirmed, onCancelled }
  },
})
</script>

<template>
  <component
    :is="componentFor(card)"
    v-bind="cardProps(card)"
    @select="onSelect"
    @action="onAction"
    @confirmed="onConfirmed"
    @cancelled="onCancelled"
  />
</template>

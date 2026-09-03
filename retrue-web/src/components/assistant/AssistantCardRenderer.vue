<script lang="ts">
/**
 * 业务卡片统一分发组件：按卡片类型渲染对应卡片，并把操作事件透传给父级。
 */

import { defineComponent } from 'vue'
import type { AssistantCard, BatchItem } from '@/api/assistant'
import type { AssistantCustomerMatch } from '@/types/api'
import BatchItemDraftCard from './BatchItemDraftCard.vue'
import BatchOverviewCard from './BatchOverviewCard.vue'
import BatchSummaryCard from './BatchSummaryCard.vue'
import CustomerPreselectedCard from './CustomerPreselectedCard.vue'
import CustomerSelectionCard from './CustomerSelectionCard.vue'
import CustomerSummaryCard from './CustomerSummaryCard.vue'
import DomainDraftCard from './DomainDraftCard.vue'
import RiskReviewCard from './RiskReviewCard.vue'
import TrainingDraftCard from './TrainingDraftCard.vue'

const TYPE_MAP = {
  batch_overview: BatchOverviewCard,
  batch_draft: BatchItemDraftCard,
  batch_summary: BatchSummaryCard,
  customer_selection: CustomerSelectionCard,
  customer_preselected: CustomerPreselectedCard,
  customer_summary: CustomerSummaryCard,
  training_draft: TrainingDraftCard,
  assessment_draft: DomainDraftCard,
  domain_draft: DomainDraftCard,
  risk_review: RiskReviewCard,
} as const

export default defineComponent({
  name: 'AssistantCardRenderer',
  components: { BatchItemDraftCard, BatchOverviewCard, BatchSummaryCard, CustomerPreselectedCard, CustomerSelectionCard, CustomerSummaryCard, TrainingDraftCard, DomainDraftCard, RiskReviewCard },
  props: {
    card: { type: Object as () => AssistantCard, required: true },
    customerId: { type: Number as () => number | null, default: null },
    courseSessionId: { type: Number as () => number | null, default: null },
  },
  emits: ['selectCustomer', 'cardAction', 'confirmed', 'cancelled', 'batchStart', 'batchCancel', 'batchAdvance', 'batchSkip'],
  setup(props, { emit }) {
    const componentFor = (card: AssistantCard) => TYPE_MAP[card.type] ?? DomainDraftCard
    const cardProps = (card: AssistantCard) => ({ card, customerId: props.customerId, courseSessionId: props.courseSessionId })

    const onSelect = (candidate: AssistantCustomerMatch) => emit('selectCustomer', props.card, candidate)
    const onAction = (action: string) => emit('cardAction', props.card, action)
    const onConfirmed = () => emit('confirmed', props.card)
    const onCancelled = () => emit('cancelled', props.card)
    const onBatchStart = (taskId: number, item: BatchItem) => emit('batchStart', props.card, taskId, item)
    const onBatchCancel = (taskId: number) => emit('batchCancel', props.card, taskId)
    const onBatchAdvance = (summary: unknown) => emit('batchAdvance', props.card, summary)
    const onBatchSkip = (summary: unknown) => emit('batchSkip', props.card, summary)

    return { componentFor, cardProps, onSelect, onAction, onConfirmed, onCancelled, onBatchStart, onBatchCancel, onBatchAdvance, onBatchSkip }
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
    @start="onBatchStart"
    @cancel="onBatchCancel"
    @advance="onBatchAdvance"
    @skip="onBatchSkip"
  />
</template>

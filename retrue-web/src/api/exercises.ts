/** 官方及个人动作目录；选择动作只填正式名称，不推断训练剂量。 */
import { request } from './http'
export interface ExerciseDefinition {
  id: number; name: string; body_part: string; description: string; precautions: string; contraindications: string; is_official: boolean
  aliases: { id?: number; alias: string }[]
  created_at?: string; updated_at?: string
}
export type ExerciseForm = Pick<ExerciseDefinition, 'name' | 'body_part' | 'description' | 'precautions' | 'contraindications' | 'aliases'>
export function apiListExercises(keyword?: string): Promise<ExerciseDefinition[]> { return request({ method: 'GET', url: '/exercises/', params: keyword ? { keyword } : undefined }) }
export function apiCreateExercise(data: ExerciseForm): Promise<ExerciseDefinition> { return request({ method: 'POST', url: '/exercises/', data }) }
export function apiUpdateExercise(id: number, data: ExerciseForm): Promise<ExerciseDefinition> { return request({ method: 'PUT', url: `/exercises/${id}/`, data }) }

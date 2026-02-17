/**
 * API Client - Re-exports from domain modules for backwards compatibility
 *
 * This file maintains the original flat export structure while delegating
 * to the modular domain files in ./domains/. New code should import directly
 * from domains for cleaner dependency trees.
 *
 * Example of new style import:
 *   import { thymosApi, grimoireApi } from '@/api/domains';
 *
 * Legacy style (still works):
 *   import { thymosApi, grimoireApi } from '@/api/client';
 */

// Re-export everything from domains
export * from './domains';

// Re-export api and API_BASE explicitly for common usage
export { api, API_BASE } from './domains/base';

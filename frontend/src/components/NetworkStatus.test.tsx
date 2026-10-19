import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, it, expect, vi } from 'vitest';
import NetworkStatus from './NetworkStatus';
import { api } from '../services/api';
vi.mock('../services/api',()=>({api:vi.fn()}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
it('shows server information once on initialisation',async()=>{
 vi.mocked(api).mockResolvedValue({ip:'93.184.216.34',country:'United Kingdom',city:'London',isp:'Example network',stale:false});
 render(<NetworkStatus/>);
 expect(await screen.findByText('93.184.216.34')).toBeVisible();
 expect(screen.getByText('London, United Kingdom')).toBeVisible();
 expect(screen.getByText('Example network')).toBeVisible();
 expect(api).toHaveBeenCalledTimes(1);
 expect(api).toHaveBeenCalledWith('/network');
 expect(screen.queryByRole('button')).toBeNull();
});
it('keeps lookup failures local to the sidebar',async()=>{
 vi.mocked(api).mockRejectedValue(new Error('offline'));
 render(<NetworkStatus/>);
 expect(await screen.findByText('Network lookup unavailable')).toBeVisible();
 expect(screen.getByText('IP unavailable')).toBeVisible();
});

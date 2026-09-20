import {render,screen,fireEvent} from '@testing-library/react';
import {vi,it,expect} from 'vitest';
vi.mock('../src/data',async()=>{const actual=await vi.importActual('../src/data');return {...actual,loadBundle:vi.fn().mockRejectedValue(new Error('No publication'))};});
import {App} from '../src/App';
it('renders honest empty states and working navigation',async()=>{
 render(<App/>);
 expect(screen.getByRole('heading',{name:'KSE-100 market outlook'})).toBeInTheDocument();
 expect(screen.getAllByText('No estimate available')).toHaveLength(2);
 await screen.findByText(/Publication check failed/);
 fireEvent.click(screen.getByRole('button',{name:'Evidence'}));
 expect(screen.getByRole('heading',{name:'No measured market results yet'})).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Health'}));
 expect(screen.getByText(/No trained model/)).toBeInTheDocument();
});
